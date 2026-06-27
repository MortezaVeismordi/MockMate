from unittest.mock import patch

from django.test import TransactionTestCase

from apps.interviews.models import InterviewSession, SessionQuestion
from apps.interviews.services import InterviewConductService
from apps.questions.models import Question
from apps.users.tests.factories import (
    InterviewMessageFactory,
    InterviewSessionFactory,
    NotificationFactory,
    QuestionCategoryFactory,
    QuestionFactory,
    QuestionOptionFactory,
    SessionQuestionFactory,
    UserAnswerFactory,
    UserFactory,
)


class TestInterviewStateMachine(TransactionTestCase):
    def setUp(self):
        self.user = UserFactory.create()
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Backend",
            status=InterviewSession.Status.SETUP,
        )
        self.q1 = QuestionFactory.create(title="Q1", body="B1", reference_answer="R1")
        self.q2 = QuestionFactory.create(title="Q2", body="B2", reference_answer="R2")

        SessionQuestionFactory.create(session=self.session, question=self.q1, order=1)
        SessionQuestionFactory.create(session=self.session, question=self.q2, order=2)

    def test_full_successful_flow(self):
        # SETUP -> INTRO
        intro_msg = InterviewConductService.start_interview(self.session)
        self.assertEqual(self.session.status, InterviewSession.Status.INTRO)
        self.assertIsNotNone(self.session.started_at)

        # INTRO -> QUESTIONING
        q_msg = InterviewConductService.ask_next_question(self.session)
        self.assertEqual(self.session.status, InterviewSession.Status.QUESTIONING)
        self.assertEqual(self.session.current_question_index, 1)

        # Answer submission triggering async task
        with patch("apps.interviews.tasks.evaluate_answer_task.delay") as mock_task:
            InterviewConductService.submit_answer(self.session, "Answer 1")
            mock_task.assert_called_once()

        sq = SessionQuestion.objects.get(session=self.session, question=self.q1)
        self.assertEqual(sq.status, SessionQuestion.QuestionStatus.ANSWERED)

        # QUESTIONING -> DRILLING
        InterviewConductService.ask_follow_up(self.session, "Expand on that?")
        self.assertEqual(self.session.status, InterviewSession.Status.DRILLING)

        # DRILLING -> QUESTIONING
        InterviewConductService.submit_follow_up_answer(self.session, "Sure, detail.")
        self.assertEqual(self.session.status, InterviewSession.Status.QUESTIONING)

        # Ask second question
        q_msg2 = InterviewConductService.ask_next_question(self.session)
        self.assertEqual(self.session.current_question_index, 2)

        # Submit second answer
        with patch("apps.interviews.tasks.evaluate_answer_task.delay"):
            InterviewConductService.submit_answer(self.session, "Answer 2")

        # QUESTIONING -> WRAP_UP
        with patch(
            "apps.interviews.tasks.generate_report_task.apply_async"
        ) as mock_gen_task:
            InterviewConductService.wrap_up(self.session)
            self.assertEqual(self.session.status, InterviewSession.Status.WRAP_UP)
            mock_gen_task.assert_called_once()

    def test_invalid_transition(self):
        # Cannot submit answer in SETUP
        with self.assertRaises(ValueError):
            InterviewConductService.submit_answer(self.session, "Answers")

        # Cannot ask followup in SETUP
        with self.assertRaises(ValueError):
            InterviewConductService.ask_follow_up(self.session, "Heres a followup")
