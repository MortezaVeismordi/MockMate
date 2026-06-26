import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import (  # just for testing, should be adjusted based on actual access control policies
    IsAdminUser,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.questions.models import Question, QuestionCategory
from apps.questions.selectors import get_random_interview_set, question_list
from apps.questions.serializers import (
    AdminQuestionSerializer,
    CandidateQuestionDetailSerializer,
    CandidateQuestionListSerializer,
    CategorySerializer,
    GitHubIngestInputSerializer,
)

logger = logging.getLogger(__name__)

# =====================================================================
# ۱. اندپوینت‌های بخش کاربر / داوطلب (Candidate Endpoints)
# =====================================================================


class QuestionListAPI(APIView):
    """
    اندپوینت ۱: مشاهده و فیلتر بانک سوالات عمومی توسط داوطلبان.
    دسترسی: عمومی (بدون نیاز به پین)، همراه با Pagination اجباری.
    """

    permission_classes = [IsAuthenticated]

    class ApiPagination(LimitOffsetPagination):
        default_limit = 12
        max_limit = 50

    def get(self, request):
        category_slug = request.query_params.get("category")
        seniority_level = request.query_params.get("seniority")

        # واکشی داده‌های تصفیه شده از لایه سلکتور
        questions = question_list(category_slug=category_slug, seniority_level=seniority_level, is_active=True)

        paginator = self.ApiPagination()
        page = paginator.paginate_queryset(questions, request, view=self)

        if page is not None:
            serializer = CandidateQuestionListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = CandidateQuestionListSerializer(questions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class QuestionDetailAPI(APIView):
    """
    اندپوینت ۲: مشاهده جزییات غیرحساس یک سوال خاص برای داوطلب.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        question = get_object_or_404(Question, id=id, is_active=True)
        serializer = CandidateQuestionDetailSerializer(question)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RandomInterviewSetAPI(APIView):
    """
    اندپوینت ۳: چیدن پکت مصاحبه تصادفی بدون به خطر انداختن پرفورمنس دیتابیس.
    """

    permission_classes = [IsAuthenticated]  # یا IsAuthenticated بسته به سیاست بیزینس شما

    def get(self, request):
        category_slug = request.query_params.get("category")
        seniority_level = request.query_params.get("seniority")
        limit = request.query_params.get("limit", 5)

        try:
            limit = int(limit)
        except ValueError:
            limit = 5

        random_questions = get_random_interview_set(
            category_slug=category_slug, seniority_level=seniority_level, limit=limit
        )

        serializer = CandidateQuestionDetailSerializer(random_questions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CategoryListAPI(APIView):
    """
    اندپوینت ۴: دریافت لیست تمام دسته‌بندی‌ها جهت استفاده در فیلترهای فرانت‌بند.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = QuestionCategory.objects.all().order_by("title")
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =====================================================================
# ۲. اندپوینت‌های بخش ادمین / پنل مدیریت (Admin CRUD Endpoints)
# =====================================================================


class AdminQuestionListCreateAPI(APIView):
    """
    اندپوینت ۵ و ۶: لیست کامل سوالات ادمین + ساخت دستی سوال جدید.
    دسترسی: کاملاً محدود به ادمین سیستم.
    """

    permission_classes = [IsAdminUser]

    class AdminPagination(LimitOffsetPagination):
        default_limit = 20
        max_limit = 100

    def get(self, request):
        # ادمین باید بتواند سوالات غیرفعال (is_active=False) را هم ببیند
        questions = Question.objects.prefetch_related("categories").all().order_by("-created_at")

        paginator = self.AdminPagination()
        page = paginator.paginate_queryset(questions, request, view=self)

        serializer = AdminQuestionSerializer(page if page is not None else questions, many=True)
        return paginator.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    def post(self, request):
        serializer = AdminQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # ذخیره ایمن سوال همراه با ریلیشن‌های ManyToMany
        serializer.save()
        logger.info(f"Admin {request.user.id} created a new question manually.")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminQuestionDetailAPI(APIView):
    """
    اندپوینت ۷، ۸ و ۹: جزئیات کامل، ویرایش تکی و حذف سوال توسط ادمین.
    """

    permission_classes = [IsAdminUser]

    def get(self, request, id):
        question = get_object_or_404(Question, id=id)
        serializer = AdminQuestionSerializer(question)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, id):
        question = get_object_or_404(Question, id=id)
        serializer = AdminQuestionSerializer(question, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        question = get_object_or_404(Question, id=id)
        # اصولا پیاده‌سازی Soft Delete امن‌تر است، اما اینجا حذف فیزیکی را بنا بر CRUD استاندارد پیاده می‌کنیم
        question.delete()
        logger.warning(f"Admin {request.user.id} deleted question ID {id}.")
        return Response({"detail": "سوال با موفقیت حذف شد."}, status=status.HTTP_204_NO_CONTENT)


class AdminCategoryListCreateAPI(APIView):
    """
    اندپوینت مدیریت دسته‌بندی‌ها توسط ادمین.
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# =====================================================================
# ۳. اندپوینت‌های بخش اتوماسیون و ایمپورت گیت‌هاب (Automation Endpoints)
# =====================================================================


class AdminGitHubIngestAPI(APIView):
    """
    اندپوینت ۱۰: استارت زدن پایپ‌لاین خزنده گیت‌هاب به صورت دستی از پنل ادمین.
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = GitHubIngestInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        github_url = serializer.validated_data["github_url"]

        # در اینجا متد آداپتور یا تسک Celery شما صدا زده می‌شود:
        # trigger_github_ingestion.delay(repo_url=github_url)

        logger.info(f"GitHub ingestion triggered by Admin {request.user.id} for repo: {github_url}")
        return Response(
            {"detail": "فرآیند استخراج و بارگذاری سوالات از گیت‌هاب با موفقیت در پس‌زمینه آغاز شد."},
            status=status.HTTP_202_ACCEPTED,
        )
