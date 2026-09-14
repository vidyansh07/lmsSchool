"""Reports, analytics, dashboards and data tools — §8.3 to §8.6.

Two rules hold across every endpoint here.

**A report is built from a scoped queryset.** The caller's own visible batches
and enrolments are resolved first, and the report runs on those. There is no
"fetch everything and filter afterwards" path, so a trainer asking for a batch
they do not teach gets an empty report rather than somebody else's numbers.

**An export is the same report, streamed.** It reuses the identical producer, so
what is downloaded and what is on screen cannot disagree, and it never holds the
whole result set in memory.
"""

from __future__ import annotations

from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability, has_capability
from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.caching import MINUTE, remember
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.permissions import IsActiveUser
from apps.common.throttling import BurstThrottle
from apps.courses import access as course_access
from apps.organisation.scoping import scope_to_branch

from . import access, dashboards, exports, importers, metrics, reports, tasks, writers
from .models import TERMINAL_EXPORT_STATUSES, BulkImport, ExportFormat, ExportJob, ExportStatus
from .serializers import (
    AdminDashboardSerializer,
    BatchOverviewSerializer,
    BatchRosterRowSerializer,
    BatchSummarySerializer,
    BulkImportSerializer,
    ExportJobRequestSerializer,
    ExportJobSerializer,
    ManagerDashboardSerializer,
    MetricSerializer,
    ReportDefinitionSerializer,
    ReportPageSerializer,
    TrainerOverviewSerializer,
    TrainerWorkloadSerializer,
    TrendPointSerializer,
    UploadSerializer,
)

REPORTS_TAG = ["reports and analytics"]

#: Rows an inline Excel or PDF export will render before refusing (19a: "small
#: lists download at once, large ones run in the background").
SYNC_ROW_LIMIT = 2_000

CONTENT_TYPES = {
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.PDF: "application/pdf",
}

#: How many rows a *screen* receives. An export streams the whole thing; a JSON
#: response does not, because a browser rendering fifty thousand rows helps
#: nobody and holding them in memory to send helps less.
PAGE_LIMIT = 500


def _forbidden(request, message: str) -> Response:
    return Response(
        {
            "error": {
                "code": "permission_denied",
                "message": message,
                "request_id": getattr(request, "request_id", "-"),
            }
        },
        status=http_status.HTTP_403_FORBIDDEN,
    )


def _filters(request):
    """Resolve `batch` and `course` inside the caller's own visibility."""
    batch = course = None
    batch_id = request.query_params.get("batch")
    course_id = request.query_params.get("course")
    if batch_id:
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
    if course_id:
        course = get_object_or_404(course_access.visible_courses(request.user), pk=course_id)
    return batch, course


#: Filters beyond batch and course that some reports take. Read from the query
#: string on a direct export and from `job.filters` on a queued one; never
#: authorization, only narrowing inside an already visible set.
EXTRA_FILTER_KEYS = ("student", "since", "until", "actor", "kind", "role")


def _extra_filters(params) -> dict:
    extra = {}
    for key in EXTRA_FILTER_KEYS:
        value = params.get(key)
        if value not in (None, ""):
            extra[key] = value
    return extra


def _queryset_for(request, source: str, batch, course, extra=None):
    """The scoped queryset a report producer expects."""
    return _queryset_for_user(request.user, source, batch, course, extra)


def _apply_student(rows, user, extra, path: str):
    """Narrow to one student, resolved inside the caller's visible students."""
    from apps.students import access as students_access

    student_id = (extra or {}).get("student")
    if not student_id:
        return rows
    student = students_access.visible_students(user).filter(pk=student_id).first()
    if student is None:
        return rows.none()
    return rows.filter(**{path: student.pk})


def _queryset_for_user(user, source: str, batch, course, extra=None):
    """The same resolution, keyed on a user rather than a request.

    Split out so `apps.reporting.tasks.run_export` can re-derive a job's
    queryset from the requesting user's *current* access without needing a
    request object — there is no request inside a worker. This is the only
    function a background export uses to build its queryset, which is what
    keeps "run it the same way the screen and the synchronous download do" true
    for the queued path as well.
    """
    if source == "batches":
        rows = batch_access.visible_batches(user)
        if batch is not None:
            rows = rows.filter(pk=batch.pk)
        if course is not None:
            rows = rows.filter(course=course)
        return rows

    if source == "trainers":
        from apps.trainers.models import TrainerProfile

        if not access.can_read_everything(user):
            # A trainer sees their own activity and nobody else's.
            trainer = batch_access.trainer_profile(user)
            return (
                TrainerProfile.objects.filter(pk=trainer.pk)
                if trainer
                else TrainerProfile.objects.none()
            )
        # Scoped to the caller's centre for the same reason the batch source
        # above is: a report that covers trainers this caller cannot open is a
        # report that leaks who works where.
        rows = scope_to_branch(TrainerProfile.objects.all(), user, path="branch")
        if batch is not None:
            rows = rows.filter(batches=batch)
        return rows.distinct()

    if source == "students":
        from apps.students import access as students_access

        rows = students_access.visible_students(user)
        if batch is not None:
            rows = rows.filter(enrollments__batch=batch)
        if course is not None:
            rows = rows.filter(enrollments__course=course)
        return _apply_student(rows.distinct(), user, extra, "pk")
    if source == "fee_payments":
        from apps.fees.models import FeePayment

        if not has_capability(user, Capability.FEE_VIEW_ANY):
            return FeePayment.objects.none()
        rows = FeePayment.objects.filter(
            plan__enrollment__in=batch_access.visible_enrollments(user)
        )
        if batch is not None:
            rows = rows.filter(plan__enrollment__batch=batch)
        if course is not None:
            rows = rows.filter(plan__enrollment__course=course)
        return _apply_student(rows, user, extra, "plan__enrollment__student_id")
    if source == "dsrs":
        from apps.dsr import access as dsr_access

        rows = dsr_access.visible_dsrs(user)
        if batch is not None:
            rows = rows.filter(batch=batch)
        if course is not None:
            rows = rows.filter(batch__course=course)
        return rows
    if source == "activity":
        from datetime import date

        from apps.activity import services as activity_services
        from apps.audit.models import AuditLog

        if not has_capability(user, Capability.AUDIT_VIEW):
            return AuditLog.objects.none()
        extra = extra or {}

        def _day(value):
            if not value:
                return None
            return value if isinstance(value, date) else date.fromisoformat(str(value))

        return activity_services.feed(
            since=_day(extra.get("since")),
            until=_day(extra.get("until")),
            actor_id=extra.get("actor") or None,
            role=extra.get("role") or None,
            kind=extra.get("kind") or None,
        )
    rows = batch_access.visible_enrollments(user)
    if batch is not None:
        rows = rows.filter(batch=batch)
    if course is not None:
        rows = rows.filter(course=course)
    return _apply_student(rows, user, extra, "student_id")


class ReportCatalogueView(APIView):
    """Which reports exist, and what each one contains."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Available reports",
        responses={200: ReportDefinitionSerializer(many=True)},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "Reports are staff-facing.")
        return Response(ReportDefinitionSerializer(reports.catalogue(), many=True).data)


class ReportView(APIView):
    """One report, as JSON, bounded to a page."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Run a report",
        parameters=[
            OpenApiParameter("batch", str),
            OpenApiParameter("course", str),
        ],
        responses={200: ReportPageSerializer},
        tags=REPORTS_TAG,
    )
    def get(self, request, key):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "Reports are staff-facing.")
        if key not in reports.REPORTS:
            raise Http404

        definition, _producer, source = reports.REPORTS[key]
        batch, course = _filters(request)
        queryset = _queryset_for(
            request, source, batch, course, _extra_filters(request.query_params)
        )

        _report, produced = reports.run(key, queryset)
        rows = []
        truncated = False
        for index, row in enumerate(produced):
            if index >= PAGE_LIMIT:
                truncated = True
                break
            rows.append(row)

        return Response(
            ReportPageSerializer(
                {
                    "key": definition.key,
                    "label": definition.label,
                    "description": definition.description,
                    "columns": definition.column_dicts(),
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": truncated,
                }
            ).data
        )


class ReportExportView(APIView):
    """The same report, streamed as CSV.

    Two gates, and both are needed.

    **You must be allowed to read the report**, by the same rule the on-screen
    view uses. This was missing: the export checked only `data.export`, so any
    role holding that capability could stream a report it could not open. That
    was harmless while every holder of `data.export` also held `report.view_any`
    — and stopped being harmless the moment a role held one without the other. A
    file is not a weaker way to read something.

    **And exporting needs its own capability** on top, because reading a page of
    a report on screen and walking out with the whole institution in a file are
    different acts.
    """

    # An export walks every visible row and streams a file; it is the most
    # expensive thing a signed-in caller can ask for.
    throttle_classes = (BurstThrottle,)

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Export a report as CSV, Excel or PDF",
        parameters=[
            OpenApiParameter("batch", str),
            OpenApiParameter("course", str),
            OpenApiParameter("student", str),
            OpenApiParameter("since", str),
            OpenApiParameter("until", str),
            OpenApiParameter("actor", str),
            OpenApiParameter("kind", str),
            OpenApiParameter("role", str),
            # `as`, not `format`: DRF reserves `?format=` for its own renderer
            # switch and answers 404 to any value it does not know.
            OpenApiParameter(
                "as",
                str,
                description=(
                    "csv (streamed, any size), xlsx or pdf (rendered inline up to "
                    f"{SYNC_ROW_LIMIT} rows; larger exports must be queued)"
                ),
            ),
        ],
        responses={
            200: OpenApiResponse(description="The file."),
            409: OpenApiResponse(description="Too many rows for an inline export; queue it."),
        },
        tags=REPORTS_TAG,
    )
    def get(self, request, key):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "Reports are staff-facing.")

        if not has_capability(request.user, Capability.DATA_EXPORT):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="report",
                resource_id=key,
                result="failure",
                context={"attempted": "report.export"},
            )
            return _forbidden(request, "You cannot export data.")
        if key not in reports.REPORTS:
            raise Http404

        definition, _producer, source = reports.REPORTS[key]
        fmt = request.query_params.get("as", ExportFormat.CSV)
        if fmt not in ExportFormat.values:
            raise ApplicationError({"as": ["Choose csv, xlsx or pdf."]})
        batch, course = _filters(request)
        extra = _extra_filters(request.query_params)
        queryset = _queryset_for(request, source, batch, course, extra)
        _report, produced = reports.run(key, queryset)

        record(
            action=AuditAction.REPORT_EXPORTED,
            actor=request.user,
            resource_type="report",
            resource_id=key,
            context={
                "batch": str(batch.pk) if batch else None,
                "course": str(course.pk) if course else None,
                "format": fmt,
                **{name: str(value) for name, value in extra.items()},
            },
            durable=False,
        )

        if fmt == ExportFormat.CSV:
            response = StreamingHttpResponse(
                exports.stream_csv(definition.column_dicts(), produced),
                content_type="text/csv; charset=utf-8",
            )
            response["Content-Disposition"] = f'attachment; filename="{exports.filename_for(key)}"'
        else:
            # Excel and PDF are rendered whole, so they are bounded: a list a
            # person is looking at fits; the whole institution goes through a
            # background job with a notification when it is ready (19a).
            rows = []
            for index, row in enumerate(produced):
                if index >= SYNC_ROW_LIMIT:
                    raise ConflictError(
                        {
                            "export": [
                                f"More than {SYNC_ROW_LIMIT:,} rows. Queue a background "
                                "export and you will be told when it is ready."
                            ]
                        }
                    )
                rows.append(row)
            content, _count = writers.write(
                fmt,
                definition.column_dicts(),
                rows,
                title=definition.label,
                filters={
                    "batch_label": batch.code if batch else None,
                    "course_label": course.title if course else None,
                    **extra,
                },
            )
            response = HttpResponse(content, content_type=CONTENT_TYPES[fmt])
            response["Content-Disposition"] = (
                f'attachment; filename="{writers.filename_for(key, fmt)}"'
            )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


# ---------------------------------------------------------------------------
# Background export jobs
# ---------------------------------------------------------------------------


def _export_job_for(request, job_id) -> ExportJob:
    """The one job, or 404 — for somebody else's id exactly as for your own.

    Filtering by ownership *before* `get_object_or_404` is what makes the two
    cases indistinguishable: a job that does not exist and a job that belongs
    to somebody else both raise the same `Http404`, the same way
    `apps.reporting.views._import_for` and
    `apps.assignments.views.SubmissionFileDownloadView` already do it. A 403
    here would tell a caller a job id is real, just not theirs — which is
    exactly the id-enumeration a 404 is meant to close off.

    That is also why `access.visible_export_jobs` narrows the
    `export.view_any` case to the caller's own centre rather than the rule
    being written out here: an administrator in Jaipur asking for a Pune job id
    must not be able to tell it from an id that names nothing.
    """
    return get_object_or_404(access.visible_export_jobs(request.user), pk=job_id)


class ExportJobQueueView(APIView):
    """Queue a report to be rendered off the request cycle, and list jobs.

    Queueing carries the same two gates as `ReportExportView`, for the same
    reason: reading a report and exporting one are different rights, and a
    role holding only one of them (the counsellor holds `data.export` without
    `report.view_any`) must be refused here exactly as it is refused there.
    Queueing does no work itself beyond validating the request and creating
    the row — `run_export` does the rest, and re-derives this same scope for
    itself rather than trusting anything decided here (see that task's
    docstring for why).

    Listing carries neither gate, so that a role whose export rights changed
    after a job was queued keeps its own history of what it asked for. It does
    still require the caller to be somebody who could own a job at all: a
    student never could, and an endpoint that is permanently empty for a role is
    better refused than politely blank.
    """

    throttle_classes = (BurstThrottle,)
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="List export jobs",
        parameters=[],
        responses={200: ExportJobSerializer(many=True)},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.could_own_an_export(request.user):
            return _forbidden(request, "Exports are staff-facing.")
        rows = access.visible_export_jobs(request.user)
        serializer = ExportJobSerializer(rows, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        summary="Queue a background export",
        request=ExportJobRequestSerializer,
        responses={202: ExportJobSerializer},
        tags=REPORTS_TAG,
    )
    def post(self, request):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "Reports are staff-facing.")
        if not has_capability(request.user, Capability.DATA_EXPORT):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="report",
                resource_id="",
                result="failure",
                context={"attempted": "export.queue"},
            )
            return _forbidden(request, "You cannot export data.")

        serializer = ExportJobRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data["report_key"]
        if key not in reports.REPORTS:
            raise Http404

        batch = course = None
        batch_id = serializer.validated_data.get("batch")
        course_id = serializer.validated_data.get("course")
        if batch_id:
            batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if course_id:
            course = get_object_or_404(course_access.visible_courses(request.user), pk=course_id)

        extra = {
            name: str(value)
            for name, value in serializer.validated_data.items()
            if name in EXTRA_FILTER_KEYS and value not in (None, "")
        }
        job = ExportJob.objects.create(
            report_key=key,
            format=serializer.validated_data["format"],
            filters={
                "batch_id": str(batch.pk) if batch else None,
                "batch_label": batch.code if batch else None,
                "course_id": str(course.pk) if course else None,
                "course_label": course.title if course else None,
                **extra,
            },
            requested_by=request.user,
            status=ExportStatus.QUEUED,
        )
        record(
            action=AuditAction.EXPORT_QUEUED,
            actor=request.user,
            resource_type="export_job",
            resource_id=job.pk,
            context={"report": key, "format": job.format},
            durable=False,
        )
        tasks.run_export.delay(str(job.pk))
        # In production this call only enqueues — `job` is still `QUEUED` when
        # the response is built, correctly. Under `CELERY_TASK_ALWAYS_EAGER`
        # (`config.settings.test`), the task above has already run against a
        # separate row fetched from the database, and this in-memory `job`
        # instance would otherwise serialise the stale values it was created
        # with. Re-reading makes the response accurate in both cases.
        job.refresh_from_db()
        return Response(
            ExportJobSerializer(job, context={"request": request}).data,
            status=http_status.HTTP_202_ACCEPTED,
        )


class ExportJobDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Export job status", responses={200: ExportJobSerializer}, tags=REPORTS_TAG
    )
    def get(self, request, job_id):
        job = _export_job_for(request, job_id)
        return Response(ExportJobSerializer(job, context={"request": request}).data)


class ExportJobDownloadView(APIView):
    """Stream a finished export. The private-storage rules apply here too:
    the application serves the download after its own authorization check,
    never a signed storage URL — see `apps.common.storage`.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download a finished export",
        responses={200: OpenApiResponse(description="The file, as an attachment.")},
        tags=REPORTS_TAG,
    )
    def get(self, request, job_id):
        job = _export_job_for(request, job_id)
        # Not ready, failed, cancelled, past its lifetime, or the file object
        # is somehow missing: every one of these reads as "not found" rather
        # than a distinguishable error, so a caller cannot use the response
        # shape to probe why a job they do not fully control isn't available.
        if (
            job.status != ExportStatus.COMPLETED
            or not job.file
            or (job.expires_at is not None and job.expires_at <= timezone.now())
        ):
            raise Http404

        record(
            action=AuditAction.EXPORT_DOWNLOADED,
            actor=request.user,
            resource_type="export_job",
            resource_id=job.pk,
            context={"report": job.report_key, "format": job.format},
            durable=False,
        )

        name = job.original_filename or writers.filename_for(job.report_key, job.format)
        response = FileResponse(
            job.file.open("rb"),
            content_type=writers.CONTENT_TYPES.get(job.format, "application/octet-stream"),
        )
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class ExportJobCancelView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Cancel an export job",
        request=None,
        responses={200: ExportJobSerializer},
        tags=REPORTS_TAG,
    )
    def post(self, request, job_id):
        job = _export_job_for(request, job_id)
        if job.status in TERMINAL_EXPORT_STATUSES:
            raise ConflictError(f"This export is already {job.get_status_display().lower()}.")

        job.status = ExportStatus.CANCELLED
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "finished_at", "updated_at"])
        record(
            action=AuditAction.EXPORT_CANCELLED,
            actor=request.user,
            resource_type="export_job",
            resource_id=job.pk,
            context={"report": job.report_key},
            durable=False,
        )
        return Response(ExportJobSerializer(job, context={"request": request}).data)


class MetricsView(APIView):
    """§8.6 — the numbers, each carrying its definition."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="LMS metrics",
        parameters=[OpenApiParameter("batch", str), OpenApiParameter("course", str)],
        responses={200: MetricSerializer(many=True)},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "Reports are staff-facing.")
        batch, course = _filters(request)
        scope = access.scope_for(request.user, batch=batch, course=course)
        return Response(MetricSerializer(metrics.compute(scope), many=True).data)


class AttendanceTrendView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Attendance by week",
        parameters=[OpenApiParameter("batch", str), OpenApiParameter("weeks", int)],
        responses={200: TrendPointSerializer(many=True)},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "Reports are staff-facing.")
        batch, course = _filters(request)
        scope = access.scope_for(request.user, batch=batch, course=course)
        weeks = max(1, min(52, int(request.query_params.get("weeks", 12))))
        return Response(
            TrendPointSerializer(metrics.attendance_trend(scope, weeks=weeks), many=True).data
        )


class AdminDashboardView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Administrator dashboard",
        responses={200: AdminDashboardSerializer},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_everything(request.user):
            return _forbidden(request, "This dashboard is for administrators.")
        data = remember(
            "dashboard:admin",
            (request.user.pk,),
            MINUTE,
            lambda: AdminDashboardSerializer(dashboards.admin_dashboard(request.user)).data,
        )
        return Response(data)


class TrainerWorkloadView(APIView):
    """What is still outstanding for the caller's batches."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My teaching workload",
        responses={200: TrainerWorkloadSerializer},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "This view is staff-facing.")
        return Response(TrainerWorkloadSerializer(dashboards.trainer_workload(request.user)).data)


class BatchSummaryView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My batches at a glance",
        responses={200: BatchSummarySerializer(many=True)},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "This view is staff-facing.")
        return Response(
            BatchSummarySerializer(dashboards.batch_summaries(request.user), many=True).data
        )


# ---------------------------------------------------------------------------
# The manager hubs
#
# Two screens the client asked for by name — Batches and Trainers — each
# drilling from a landing summary down to one record's full picture. Routed
# under `dashboard_urlpatterns` alongside the views above: this app's routes
# are mounted at `reports/` and `dashboards/` only (see `urls.py`), so the
# batch and trainer drill-downs live at `/batches/<id>/...` and
# `/trainers/<id>/...` rather than under a bare `/batches/` or
# `/trainers/` prefix this app does not own.
# ---------------------------------------------------------------------------


class ManagerDashboardView(APIView):
    """The two hubs' landing summary — a KPI strip and the attention queue."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Manager hub summary",
        responses={200: ManagerDashboardSerializer},
        tags=REPORTS_TAG,
    )
    def get(self, request):
        if not access.can_read_manager_hubs(request.user):
            return _forbidden(request, "This dashboard is for administrators and managers.")
        data = remember(
            "dashboard:manager",
            (request.user.pk,),
            MINUTE,
            lambda: ManagerDashboardSerializer(dashboards.manager_dashboard(request.user)).data,
        )
        return Response(data)


class BatchOverviewView(APIView):
    """Everything about one batch — the batches hub's drill-down."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Batch overview",
        responses={200: BatchOverviewSerializer},
        tags=REPORTS_TAG,
    )
    def get(self, request, batch_id):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "This view is staff-facing.")
        batch = get_object_or_404(access.visible_batches(request.user), pk=batch_id)
        return Response(BatchOverviewSerializer(dashboards.batch_overview(batch)).data)


class BatchStudentsView(ListAPIView):
    """A batch's roster, one rollup row per student — the batch overview's own drill-down."""

    permission_classes = (IsActiveUser,)
    serializer_class = BatchRosterRowSerializer
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = (
        "student__student_id",
        "student__user__first_name",
        "student__user__last_name",
        "student__user__email",
    )
    ordering_fields = (
        "student__user__first_name",
        "student__user__last_name",
        "status",
        "enrolled_at",
    )
    ordering = ("student__user__first_name", "student__user__last_name")

    def get_queryset(self):
        batch = get_object_or_404(
            access.visible_batches(self.request.user), pk=self.kwargs["batch_id"]
        )
        return dashboards.roster_queryset(batch)

    @extend_schema(
        summary="Batch roster with per-student rollups",
        parameters=[OpenApiParameter("search", str), OpenApiParameter("ordering", str)],
        responses={200: BatchRosterRowSerializer(many=True)},
        tags=REPORTS_TAG,
    )
    def list(self, request, *args, **kwargs):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "This view is staff-facing.")
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = dashboards.batch_roster_rows(list(page if page is not None else queryset))
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class TrainerOverviewView(APIView):
    """Everything about one trainer — the trainers hub's drill-down."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Trainer overview",
        responses={200: TrainerOverviewSerializer},
        tags=REPORTS_TAG,
    )
    def get(self, request, trainer_id):
        if not access.can_read_reports(request.user):
            return _forbidden(request, "This view is staff-facing.")
        trainer = get_object_or_404(access.visible_trainers(request.user), pk=trainer_id)
        return Response(
            TrainerOverviewSerializer(
                dashboards.trainer_overview(trainer, viewer=request.user)
            ).data
        )


# ---------------------------------------------------------------------------
# Bulk import — §8.5
# ---------------------------------------------------------------------------


def _may_import(request) -> bool:
    return has_capability(request.user, Capability.DATA_IMPORT)


class StudentImportView(APIView):
    """Step one for a student file: read, validate, report. Writes nothing."""

    # Parsing a spreadsheet is CPU work on caller-supplied input.
    throttle_classes = (BurstThrottle,)

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Preview a student import",
        request=UploadSerializer,
        responses={201: BulkImportSerializer},
        tags=REPORTS_TAG,
    )
    def post(self, request):
        if not _may_import(request):
            return _forbidden(request, "You cannot import data.")

        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        batch = None
        batch_id = serializer.validated_data.get("batch")
        if batch_id:
            batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)

        run = importers.preview_students(
            actor=request.user, uploaded_file=serializer.validated_data["file"], batch=batch
        )
        return Response(BulkImportSerializer(run).data, status=http_status.HTTP_201_CREATED)


class AttendanceImportView(APIView):
    """Step one for a register taken on paper."""

    # Parsing a spreadsheet is CPU work on caller-supplied input.
    throttle_classes = (BurstThrottle,)

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Preview an attendance import",
        request=UploadSerializer,
        responses={201: BulkImportSerializer},
        tags=REPORTS_TAG,
    )
    def post(self, request, session_id):
        from apps.sessions import access as session_access

        if not _may_import(request):
            return _forbidden(request, "You cannot import data.")

        session = get_object_or_404(session_access.visible_sessions(request.user), pk=session_id)
        if not session_access.can_take_attendance(request.user, session):
            return _forbidden(request, "You cannot mark this class.")

        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = importers.preview_attendance(
            actor=request.user, session=session, uploaded_file=serializer.validated_data["file"]
        )
        return Response(BulkImportSerializer(run).data, status=http_status.HTTP_201_CREATED)


def _import_for(request, import_id) -> BulkImport:
    """The one resolver behind the detail, confirm and reject routes.

    Out of the access queryset, so an id from another centre is a 404 on all
    three rather than a 200 on the first and a mutation on the other two.
    """
    return get_object_or_404(access.visible_bulk_imports(request.user), pk=import_id)


class ImportDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="An import preview", responses={200: BulkImportSerializer}, tags=REPORTS_TAG
    )
    def get(self, request, import_id):
        if not _may_import(request):
            return _forbidden(request, "You cannot import data.")
        return Response(BulkImportSerializer(_import_for(request, import_id)).data)


class ImportConfirmView(APIView):
    """Step two: apply it, all or nothing."""

    # Confirmation writes every row in one transaction.
    throttle_classes = (BurstThrottle,)

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Confirm an import",
        request=None,
        responses={200: BulkImportSerializer},
        tags=REPORTS_TAG,
    )
    def post(self, request, import_id):
        if not _may_import(request):
            return _forbidden(request, "You cannot import data.")

        run = _import_for(request, import_id)
        from .models import ImportKind

        if run.kind == ImportKind.STUDENTS:
            run = importers.confirm_students(run=run, actor=request.user)
        else:
            run = importers.confirm_attendance(run=run, actor=request.user)
        return Response(BulkImportSerializer(run).data)


class ImportRejectView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Discard an import",
        request=None,
        responses={200: BulkImportSerializer},
        tags=REPORTS_TAG,
    )
    def post(self, request, import_id):
        if not _may_import(request):
            return _forbidden(request, "You cannot import data.")
        run = importers.reject(run=_import_for(request, import_id), actor=request.user)
        return Response(BulkImportSerializer(run).data)
