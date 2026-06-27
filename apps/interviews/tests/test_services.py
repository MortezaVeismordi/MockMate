from unittest.mock import patch

from django.test import TransactionTestCase

from apps.interviews.models import (InterviewSession, SessionQuestion,
                                    UserAnswer)
from apps.interviews.services import (EvaluationService,
                                      InterviewConductService,
                                      InterviewSetupService, ReportService)
from apps.questions.models import Question, QuestionCategory
from apps.users.tests.factories import (InterviewMessageFactory,
                                        InterviewSessionFactory,
                                        NotificationFactory,
                                        QuestionCategoryFactory,
                                        QuestionFactory, QuestionOptionFactory,
                                        SessionQuestionFactory,
                                        UserAnswerFactory, UserFactory)


class TestInterviewServices(TransactionTestCase):
    def setUp(self):
        self.user = UserFactory.create(phone_number="09112223344")
        cat = QuestionCategoryFactory.create(title="Backend", slug="backend")

        # Create some dummy questions
        for i in range(3):
            q = QuestionFactory.create(
                title=f"Q{i}",
                body=f"Body {i}",
                seniority_level=Question.SeniorityLevel.MID_LEVEL,
                question_type=Question.QuestionType.TECHNICAL,
            )
            q.categories.add(cat)

    def test_session_creation_success(self):
        session = InterviewSetupService.create_session(
            user=self.user,
            target_position="Django Dev",
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            total_questions=2,
        )
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.status, InterviewSession.Status.SETUP)
        self.assertEqual(session.session_questions.count(), 2)

    def test_session_creation_fails_with_active_session(self):
        InterviewSessionFactory.create(
            user=self.user,
            target_position="Dev",
            status=InterviewSession.Status.QUESTIONING,
        )
        with self.assertRaises(ValueError) as ctx:
            InterviewSetupService.create_session(
                user=self.user, target_position="Dev2", seniority_level="mid_level"
            )
        self.assertIn("یک مصاحبه فعال دارید", str(ctx.exception))

    def test_question_allocation_logic(self):
        questions = InterviewSetupService._select_questions(
            seniority_level=Question.SeniorityLevel.MID_LEVEL,
            focus_topics=["backend"],
            total=2,
        )
        self.assertEqual(len(questions), 2)

    def test_eval_service_success(self):
        session = InterviewSessionFactory.create(user=self.user, target_position="Dev")
        q = Question.objects.first()
        answer = UserAnswerFactory.create(
            session=session,
            user=self.user,
            question=q,
            answer_text="Test",
            status=UserAnswer.Status.PENDING,
        )

        mock_eval_result = {
            "score": 90,
            "technical_accuracy": "Very good",
            "strengths": ["Clear"],
            "weaknesses": ["None"],
        }

        with patch(
            "apps.core.llm.client.LLMClient.evaluate", return_value=mock_eval_result
        ):
            graded_answer = EvaluationService.evaluate_answer(answer)

        self.assertEqual(graded_answer.status, UserAnswer.Status.GRADED)
        self.assertEqual(graded_answer.score, 90)
        self.assertEqual(graded_answer.strengths, ["Clear"])

    @patch(
        "apps.core.llm.client.LLMClient.generate_report_summary",
        return_value="Great job",
    )
    def test_report_service_aggregates_results(self, mock_report_gen):
        session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Dev",
            status=InterviewSession.Status.WRAP_UP,
        )
        q1 = Question.objects.all()[0]
        q2 = Question.objects.all()[1]

        UserAnswerFactory.create(
            session=session,
            user=self.user,
            question=q1,
            score=80,
            status=UserAnswer.Status.GRADED,
        )
        UserAnswerFactory.create(
            session=session,
            user=self.user,
            question=q2,
            score=90,
            status=UserAnswer.Status.GRADED,
        )

        updated_session = ReportService.generate_final_report(session)
        self.assertEqual(updated_session.status, InterviewSession.Status.COMPLETED)
        self.assertEqual(updated_session.final_score, 85.0)
        self.assertEqual(updated_session.summary, "Great job")
