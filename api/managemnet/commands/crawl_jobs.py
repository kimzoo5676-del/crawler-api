from django.core.management.base import BaseCommand

from api.crawler import crawl
from api.models import JobPosting


class Command(BaseCommand):
    help = "fake-jobs 사이트에서 채용공고를 수집해 DB에 저장"

    def handle(self, *args, **options):
        jobs = crawl()
        created_count = 0
        updated_count = 0

        for job in jobs:
            obj, created = JobPosting.objects.update_or_create(
                url=job["url"],
                defaults={
                    "title": job["title"],
                    "company": job["company"],
                    "location": job["location"],
                    "source": job["source"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"완료 - 생성 {created_count}개, 갱신 {updated_count}개")
        )
