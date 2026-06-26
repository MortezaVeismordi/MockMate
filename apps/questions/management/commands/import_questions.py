import traceback

from django.core.management.base import BaseCommand, CommandError

from apps.questions.ingestion.pipeline import QuestionIngestionPipeline


class Command(BaseCommand):
    help = 'ایمپورت انترپرایز، فیلتر شده و هوشمند سوالات مصاحبه از گیت‌هاب به دیتابیس'

    def add_arguments(self, parser):
        # آرگومان اجباری: نام آداپتور (مثلا: devops یا awesome)
        parser.add_argument(
            'adapter_name',
            type=str,
            help='نام آداپتور ثبت شده در سیستم (مثال: devops)'
        )

        # پارامترهای اختیاری و پیشرفته برای کاستومایز کردن فرآیند استخراج
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='سقف تعداد سوالاتی که می‌خواهید وارد دیتابیس شوند (مناسب برای تست سریع)'
        )
        parser.add_argument(
            '--path',
            type=str,
            default=None,
            help='مسیر یک پوشه خاص در ریپو برای پارس کردن اختصاصی (مثال: docker)'
        )
        parser.add_argument(
            '--category',
            type=str,
            default=None,
            help='فیلتر دقیق روی نام دپارتمان یا دسته‌بندی استخراج شده'
        )
        parser.add_argument(
            '--level',
            type=str,
            default=None,
            choices=['junior', 'mid_level', 'senior'],
            help='فیلتر بر اساس سطح سختی و ارشدیت سوالات'
        )

    def handle(self, *args, **options):
        adapter_name = options['adapter_name']

        # چاپ پیام خوش‌آمدگویی و استارت با رنگ زرد (WARNING) در ترمینال
        self.stdout.write(self.style.WARNING(f"\n🚀 Initializing Ingestion Pipeline for: '{adapter_name}'..."))
        self.stdout.write(self.style.NOTICE("--------------------------------------------------"))

        try:
            # ۱. ساخت نمونه از ارکستراتور اصلی و پاس دادن آرگومان‌های خط فرمان
            pipeline = QuestionIngestionPipeline(
                adapter_name=adapter_name,
                limit=options['limit'],
                sub_path=options['path'],
                category=options['category'],
                level=options['level']
            )

            # ۲. شلیک فرآیند استخراج، تبدیل و بارگذاری (ETL)
            saved_count = pipeline.run()

            # ۳. بررسی خروجی نهایی و فیدبک مناسب به توسعه‌دهنده
            self.stdout.write(self.style.NOTICE("--------------------------------------------------"))
            if saved_count > 0:
                success_msg = f"🟢 Success! {saved_count} questions have been successfully integrated into PostgreSQL."
                self.stdout.write(self.style.SUCCESS(success_msg))
            else:
                warn_msg = "🟡 Pipeline executed, but 0 questions were loaded. (Check filters or repo logs)."
                self.stdout.write(self.style.WARNING(warn_msg))

        except ValueError as val_err:
            # خطای مربوط به نام اشتباه آداپتور
            self.stdout.write(self.style.ERROR(f"❌ Configuration Error: {str(val_err)}"))

        except Exception as e:
            # هک و مدیریت خطاهای پیش‌بینی نشده سیستمی همراه با Traceback در صورت نیاز به دیباگ
            self.stdout.write(self.style.ERROR(f"💥 Fatal error during command execution: {str(e)}"))
            self.stdout.write(self.style.NOTICE(traceback.format_exc()))
            raise CommandError("Ingestion command failed catastrophically.")
