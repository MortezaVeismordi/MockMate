import logging
import os
import subprocess
from typing import Optional

# وارد کردن آداپتورها
from .devops_adapter import DevOpsExercisesAdapter

logger = logging.getLogger(__name__)


class QuestionIngestionPipeline:
    """
    ارکستراتور و مدیریت‌کننده کلان خط لوله پورت داده‌ها از گیت‌هاب.
    وظایف: مدیریت فیزیکی ریپوها روی دیسک، نگاشت نام آداپتور به کلاس مربوطه و اجرای ETL.
    """

    # مپ کردن نام‌های ورودی ترمینال به ریپوزیوری‌های واقعی گیت‌هاب
    REPO_REGISTRY = {
        "devops": {
            "url": "https://github.com/bregman-arie/devops-exercises.git",
            "dir_name": "devops-exercises",
            "adapter_class": DevOpsExercisesAdapter,
        },
        "awesome": {
            "url": "https://github.com/0xAX/linux-insides.git",  # به عنوان نمونه برای awesome
            "dir_name": "awesome-questions",
            "adapter_class": None,  # بعداً تکمیل می‌شود
        },
    }

    def __init__(
        self,
        adapter_name: str,
        limit: Optional[int] = None,
        sub_path: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
    ):
        self.adapter_name = adapter_name.lower()
        self.limit = limit
        self.sub_path = sub_path
        self.category = category
        self.level = level

        if self.adapter_name not in self.REPO_REGISTRY:
            raise ValueError(f"Adapter '{adapter_name}' is not registered in the pipeline.")

        self.repo_config = self.REPO_REGISTRY[self.adapter_name]

        # تعیین پوشه محلی برای دانلود ریپوها (داخل کانتینر در مسیر /app/downloads)
        self.base_download_dir = os.path.join(os.getcwd(), "downloads")
        self.local_repo_path = os.path.join(self.base_download_dir, self.repo_config["dir_name"])

    def _setup_repository(self):
        """
        نسخه انترپرایز و مقاوم در برابر اختلال شبکه.
        اگر کلون گیت شکست بخورد، به طور خودکار از دانلود مستقیم Zip استفاده می‌کند.
        """
        if not os.path.exists(self.base_download_dir):
            os.makedirs(self.base_download_dir)

        if not os.path.exists(self.local_repo_path):
            logger.info(f"Trying to clone repository via Git: {self.repo_config['url']}...")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", self.repo_config["url"], self.local_repo_path],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                logger.info("Git clone completed successfully.")
            except subprocess.CalledProcessError:
                logger.warning("Git clone failed due to network/TLS issues. Switching to Zip Download alternative...")
                self._download_via_zip()
        else:
            logger.info("Repository exists locally. Proceeding with existing data...")

    def _download_via_zip(self):
        """
        دانلود مستقیم فایل Zip ریپو و اکسترکت کردن آن در مسیر مورد نظر پروژه
        """
        import shutil
        import zipfile

        # تبدیل آدرس ریپو به لینک دانلود مستقیم زیپ از گیت‌هاب
        zip_url = self.repo_config["url"].replace(".git", "/archive/refs/heads/master.zip")
        # در برخی ریپوها شاخه اصلی main است
        if "devops-exercises" in zip_url:
            zip_url = self.repo_config["url"].replace(".git", "/archive/refs/heads/master.zip")

        temp_zip_path = os.path.join(self.base_download_dir, "repo.zip")
        extracted_temp_dir = os.path.join(self.base_download_dir, "temp_extracted")

        logger.info(f"Downloading ZIP fallback from: {zip_url}")
        try:
            # استفاده از curl بومی داخل کانتینر (که قبلا در داکرفایل نصب کردیم)
            subprocess.run(
                ["curl", "-L", zip_url, "-o", temp_zip_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            logger.info("Extracting ZIP archive...")
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                zip_ref.extractall(extracted_temp_dir)

            # گیت‌هاب پوشه را با نام ریپو + اسم برانچ اکسترکت می‌کند (مثلا devops-exercises-master)
            extracted_folder_name = os.listdir(extracted_temp_dir)[0]
            full_extracted_path = os.path.join(extracted_temp_dir, extracted_folder_name)

            # جابجایی به مسیر استاندارد خط لوله
            if os.path.exists(self.local_repo_path):
                shutil.rmtree(self.local_repo_path)
            shutil.move(full_extracted_path, self.local_repo_path)
            logger.info("ZIP Extraction and alignment completed successfully.")

        except Exception as e:
            logger.error(f"ZIP Fallback also failed: {str(e)}")
            raise e
        finally:
            # تمیزکاری دیسک کانتینر
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            if os.path.exists(extracted_temp_dir):
                shutil.rmtree(extracted_temp_dir)

    def run(self) -> int:
        """
        نقطه شروع عملیات ارکستراسیون.
        """
        # ۱. آماده‌سازی ریپو روی دیسک
        try:
            # در فاز لوکال/تست اگر مایل نبودی کلون واقعی انجام شود، این متد را کامنت کن و فایل را دستی بریز
            self._setup_repository()
        except Exception:
            logger.error("Skipping repository setup due to git error, trying to parse existing workspace...")

        # ۲. یافتن آداپتور متناظر (Factory Pattern)
        adapter_class = self.repo_config["adapter_class"]
        if not adapter_class:
            logger.error(f"Adapter class for '{self.adapter_name}' is not implemented yet!")
            return 0

        # ۳. نیو کردن آداپتور و پاس دادن کانتکست داینامیک ترمینال
        adapter_instance = adapter_class(
            repo_path=self.local_repo_path,
            limit=self.limit,
            sub_path=self.sub_path,
            category=self.category,
            level=self.level,
        )

        # ۴. جادوی اصلی: سپردن کار به لایه لودر کلاس پایه
        total_saved = adapter_instance.run_pipeline()
        return total_saved
