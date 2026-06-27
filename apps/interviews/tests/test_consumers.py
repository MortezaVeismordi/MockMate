import json
from unittest.mock import MagicMock, patch

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from apps.interviews.consumers import InterviewConsumer
from apps.interviews.models import InterviewSession
from apps.users.tests.factories import (
    InterviewSessionFactory,
    QuestionFactory,
    SessionQuestionFactory,
    UserFactory,
)


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class InterviewConsumerTest(TransactionTestCase):
    def setUp(self):
        self.user = UserFactory.create(
            email="test@example.com", first_name="Test", last_name="User"
        )
        self.session = InterviewSessionFactory.create(
            user=self.user,
            target_position="Senior Django Developer",
            seniority_level="senior",
            job_description="Develop Django applications",
            focus_topics=["Django", "PostgreSQL"],
            total_questions=2,
            status=InterviewSession.Status.SETUP,
        )
        self.question = QuestionFactory.create()
        self.session_question = SessionQuestionFactory.create(
            session=self.session, question=self.question, order=1
        )

    async def _get_communicator(self, user=None, session_uuid=None):
        if user is None:
            user = self.user
        if session_uuid is None:
            session_uuid = self.session.uuid

        communicator = WebsocketCommunicator(
            InterviewConsumer.as_asgi(), f"/ws/interviews/{session_uuid}/"
        )
        communicator.scope["user"] = user
        communicator.scope["url_route"] = {"kwargs": {"uuid": str(session_uuid)}}
        return communicator

    async def test_connect_success(self):
        """Test successful WebSocket connection"""
        communicator = await self._get_communicator()
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "connected")
        # ✅ مقدار واقعی که consumer می‌فرسته "setup" هست، نه "ready"
        self.assertEqual(response["payload"]["status"], "setup")

        await communicator.disconnect()

    async def test_connect_unauthenticated(self):
        communicator = WebsocketCommunicator(
            InterviewConsumer.as_asgi(), f"/ws/interviews/{self.session.uuid}/"
        )
        communicator.scope["user"] = AnonymousUser()
        communicator.scope["url_route"] = {"kwargs": {"uuid": str(self.session.uuid)}}

        connected, subprotocol = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_connect_invalid_session(self):
        invalid_uuid = "00000000-0000-0000-0000-000000000000"
        communicator = WebsocketCommunicator(
            InterviewConsumer.as_asgi(), f"/ws/interviews/{invalid_uuid}/"
        )
        communicator.scope["user"] = self.user
        communicator.scope["url_route"] = {"kwargs": {"uuid": invalid_uuid}}

        connected, subprotocol = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_handle_start_event(self):
        """Test handling start event"""
        mock_msg = MagicMock()
        mock_msg.content = "Welcome to your interview."
        mock_msg.turn_number = 1

        # ✅ patch روی متد استاتیک، نه کلاس — چون database_sync_to_async sync هست
        with patch(
            "apps.interviews.services.InterviewConductService.start_interview",
            return_value=mock_msg,
        ):
            communicator = await self._get_communicator()
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()  # connected

            await communicator.send_json_to({"type": "start", "payload": {}})

            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "greeting")
            self.assertEqual(
                response["payload"]["content"], "Welcome to your interview."
            )

            await communicator.disconnect()

    async def test_handle_next_question_event(self):
        """Test handling next_question event"""
        mock_result = MagicMock()
        mock_result.message_type = "question"
        mock_result.content = "What is Django?"
        mock_result.turn_number = 2
        mock_result.metadata = {"question_order": 1, "estimated_time": 120}
        mock_result.related_question = MagicMock()
        mock_result.related_question.question.question_type = "technical"
        mock_result.related_question.question.code_template = None

        # ✅ session باید status=INTRO داشته باشه وگرنه consumer ریجکت می‌کنه
        self.session.status = InterviewSession.Status.INTRO
        await self.session.asave()

        with patch(
            "apps.interviews.services.InterviewConductService.ask_next_question",
            return_value=mock_result,
        ):
            communicator = await self._get_communicator()
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()  # connected

            await communicator.send_json_to({"type": "next_question", "payload": {}})

            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "question")
            self.assertEqual(response["payload"]["content"], "What is Django?")
            self.assertEqual(response["payload"]["question_order"], 1)

            await communicator.disconnect()

    async def test_handle_submit_answer_event(self):
        """Test handling submit_answer event"""
        mock_answer = MagicMock()
        mock_answer.pk = 1
        mock_answer.status = "pending"

        # ✅ باید QUESTIONING باشه
        self.session.status = InterviewSession.Status.QUESTIONING
        await self.session.asave()

        with patch(
            "apps.interviews.services.InterviewConductService.submit_answer",
            return_value=mock_answer,
        ):
            communicator = await self._get_communicator()
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()  # connected

            await communicator.send_json_to(
                {
                    "type": "submit_answer",
                    "payload": {
                        "question_id": self.question.id,
                        "answer_text": "Django is a web framework for building web applications.",
                        "answer_duration": 30,
                    },
                }
            )

            response1 = await communicator.receive_json_from()
            self.assertEqual(response1["type"], "answer_received")
            self.assertEqual(response1["payload"]["answer_id"], 1)

            response2 = await communicator.receive_json_from()
            self.assertEqual(response2["type"], "evaluating")

            await communicator.disconnect()

    async def test_handle_submit_follow_up_event(self):
        """Test handling submit_follow_up event"""
        # ✅ باید DRILLING باشه
        self.session.status = InterviewSession.Status.DRILLING
        await self.session.asave()

        with patch(
            "apps.interviews.services.InterviewConductService.submit_follow_up_answer",
            return_value=None,
        ):
            communicator = await self._get_communicator()
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()  # connected

            await communicator.send_json_to(
                {
                    "type": "submit_follow_up",
                    "payload": {
                        "question_id": self.question.id,
                        "answer_text": "Follow up answer text here",
                        "answer_duration": 20,
                    },
                }
            )

            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "answer_received")

            await communicator.disconnect()

    async def test_channel_layer_evaluation_done(self):
        """Test receiving evaluation_done event from channel layer"""
        communicator = await self._get_communicator()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()  # connected

        # ✅ channel_layer رو مستقیم از channels بگیر، نه از communicator
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"interview_{self.session.uuid}",
            {
                "type": "interview.evaluation.done",
                "data": {"score": 85, "feedback": "Good job"},
            },
        )

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "evaluation_done")
        self.assertEqual(response["payload"]["score"], 85)

        await communicator.disconnect()

    async def test_disconnect(self):
        communicator = await self._get_communicator()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()  # connected
        await communicator.disconnect()
