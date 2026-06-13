from rest_framework import serializers
from apps.questions.models import Question, QuestionCategory

# =====================================================================
# ۱. سریالایزرهای مشترک و عمومی (Shared / Helper Serializers)
# =====================================================================

class CategorySerializer(serializers.ModelSerializer):
    """
    نمایش اطلاعات پایه و عمومی هر دسته‌بندی.
    """
    class Meta:
        model = QuestionCategory
        fields = ['id', 'title', 'slug', 'description']
        read_only_fields = ['id', 'slug']


# =====================================================================
# ۲. سریالایزرهای بخش کاربر / داوطلب (Candidate Serializers)
# =====================================================================

class CandidateQuestionListSerializer(serializers.ModelSerializer):
    """
    اندپوینت ۱: نمایش لیستی سوالات برای داوطلبان.
    بسیار سبک و بهینه بدون فیلدهای متنی سنگین.
    """
    categories = CategorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Question
        fields = [
            'id', 
            'title', 
            'question_type', 
            'seniority_level', 
            'estimated_time', 
            'categories'
        ]


class CandidateQuestionDetailSerializer(serializers.ModelSerializer):
    """
    اندپوینت ۲ و ۳: نمایش جزئیات کامل سوال در زمان آزمون یا شبیه‌ساز تصادفی.
    فیلدهایی مثل پاسخ مرجع یا ارزیابی هوش مصنوعی برای جلوگیری از تقلب داوطلب مخفی هستند.
    """
    categories = CategorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Question
        fields = [
            'id',
            'title',
            'body',
            'estimated_time',
            'code_template',
            'question_type',
            'seniority_level',
            'categories'
        ]


# =====================================================================
# ۳. سریالایزرهای بخش ادمین / پنل مدیریت (Admin / Backoffice Serializers)
# =====================================================================

class AdminQuestionSerializer(serializers.ModelSerializer):
    """
    اندپوینت‌های ۵، ۶ و ۷: مدیریت کامل سوالات (CRUD) توسط ادمین سیستم.
    دسترسی کامل به فیلدهای حساس مانند پاسخ مرجع و منطق هوش مصنوعی.
    """
    categories = CategorySerializer(many=True, read_only=True)
    # دریافت آی‌دی دسته‌بندی‌ها به صورت آرایه‌ای در زمان ساخت یا ویرایش
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=QuestionCategory.objects.all(),
        write_only=True,
        many=True,
        source='categories'
    )

    class Meta:
        model = Question
        fields = [
            'id',
            'title',
            'body',
            'estimated_time',
            'code_template',
            'question_type',
            'seniority_level',
            'reference_answer',
            'ai_evaluation_criteria',
            'is_active',
            'source',
            'source_url',
            'categories',
            'category_ids',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_ai_evaluation_criteria(self, value):
        """
        اعتبارسنجی اختصاصی ادمین: مطمئن می‌شویم دیتای ساختاریافته هوش مصنوعی حتماً یک دیکشنری JSON معتبر باشد.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("معیارهای ارزیابی هوش مصنوعی باید به صورت ساختار کلید-مقدار (JSON) ارسال شوند.")
        return value


# =====================================================================
# ۴. سریالایزرهای بخش اتوماسیون و ایمپورت (Automation Serializers)
# =====================================================================

class GitHubIngestInputSerializer(serializers.Serializer):
    """
    اندپوینت ۱۰: دریافت و اعتبارسنجی ورودی‌های خزنده خودکار از گیت‌هاب.
    """
    github_url = serializers.URLField(
        required=True, 
        help_text="آدرس کامل ریپوزیوری گیت‌هاب برای استخراج سوالات"
    )
    
    def validate_github_url(self, value):
        if "github.com" not in value.lower():
            raise serializers.ValidationError("آدرس ارسالی باید یک لینک معتبر از دامنه github.com باشد.")
        return value