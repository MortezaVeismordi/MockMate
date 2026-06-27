# apps/users/tests/factories.py
import factory
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from factory.fuzzy import FuzzyChoice

from apps.interviews.models import (
    InterviewMessage,
    InterviewSession,
    SessionQuestion,
    UserAnswer,
)
from apps.notifications.models import Notification
from apps.questions.models import (
    Question,
    QuestionAttachment,
    QuestionCategory,
    QuestionOption,
)

# ── ایمپورت مدل‌ها با نام‌های دقیق و واقعی پروژه ────────────────────────
from apps.users.models import CustomUser as User
from apps.users.models import OTPCode

# ==========================================
# 1. User & Auth Factories
# ==========================================


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("phone_number",)

    # فیلد اصلی لاگین شماره تلفن است
    phone_number = factory.Sequence(lambda n: f"0912{n:07d}")
    email = factory.Sequence(lambda n: f"testuser_{n}@mockmate.com")
    password = factory.LazyFunction(lambda: make_password("TestPass123!"))
    is_active = True
    is_staff = False
    is_phone_verified = True  # برای عبور راحت از تست‌های احراز هویت


class OTPCodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OTPCode

    user = factory.SubFactory(UserFactory)
    code = "123456"
    purpose = "login"
    is_used = False
    failed_attempts = 0


# ==========================================
# 2. Questions Factories (دقیقاً مطابق مدل جدید)
# ==========================================


class QuestionCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QuestionCategory
        django_get_or_create = ("slug",)

    title = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    description = "Test category description"


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Question

    title = factory.Sequence(lambda n: f"Test Question {n}")
    body = factory.Faker("text", max_nb_chars=500)
    reference_answer = factory.Faker("text", max_nb_chars=500)
    question_type = "technical"
    seniority_level = "mid_level"
    estimated_time = 120
    is_active = True


class QuestionOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QuestionOption

    question = factory.SubFactory(QuestionFactory)
    text = factory.Sequence(lambda n: f"Option {n}")
    is_correct = False


class QuestionAttachmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QuestionAttachment

    question = factory.SubFactory(QuestionFactory)
    # نکته: برای فایل‌ها در تست‌ها بهتر است از فایل جعلی استفاده شود
    # اما چون احتمالاً تست‌های شما فایل آپلود نمی‌کنند، یک نام فرضی می‌گذاریم
    file = factory.django.FileField(filename="test_config.yml")


# ==========================================
# 3. Interviews Factories
# ==========================================


class InterviewSessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InterviewSession

    user = factory.SubFactory(UserFactory)
    target_position = "Senior Django Developer"
    seniority_level = "senior"
    status = "setup"
    total_questions = 5


class SessionQuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SessionQuestion

    session = factory.SubFactory(InterviewSessionFactory)
    question = factory.SubFactory(QuestionFactory)
    order = factory.Sequence(lambda n: n + 1)
    status = "pending"


class InterviewMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InterviewMessage

    session = factory.SubFactory(InterviewSessionFactory)
    role = "assistant"
    message_type = "question"
    content = factory.Faker("text", max_nb_chars=300)
    turn_number = factory.Sequence(lambda n: n + 1)


class UserAnswerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAnswer

    session = factory.SubFactory(InterviewSessionFactory)
    user = factory.SubFactory(UserFactory)
    question = factory.SubFactory(QuestionFactory)
    answer_text = factory.Faker("text", max_nb_chars=800)
    status = "pending"


# ==========================================
# 4. Notifications Factory
# ==========================================


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    type = FuzzyChoice(["email", "sms", "push"])
    payload = factory.LazyFunction(
        lambda: {"subject": "Test Subject", "body": "Test Body"}
    )
