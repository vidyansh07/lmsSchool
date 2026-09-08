/**
 * Types mirroring the backend API contract (see backend/config/api_urls.py and
 * the OpenAPI schema at /api/schema/).
 *
 * Hand-written and deliberately narrow: only what the frontend consumes. Once
 * the surface grows further, generate this file from the OpenAPI document so
 * the two cannot drift.
 */

export type UserRole =
  | 'superadmin'
  | 'admin'
  | 'manager'
  | 'counsellor'
  | 'trainer'
  | 'student';

export type FeeStatus = 'pending' | 'partial' | 'paid' | 'waived' | 'overdue';

export type Qualification =
  | 'secondary'
  | 'higher_secondary'
  | 'diploma'
  | 'bachelors'
  | 'masters'
  | 'other';

export type InstitutionKind = 'college' | 'employer';

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  role: UserRole;
  is_active: boolean;
  is_email_verified: boolean;
  profile_image_url: string | null;
  date_joined: string;
}

/**
 * The signed-in user. `capabilities` drives what the UI offers.
 *
 * It is a rendering hint only — the backend re-checks every capability on every
 * request, so a tampered list gains nothing.
 */
export interface CurrentUser extends User {
  last_login: string | null;
  email_verified_at: string | null;
  capabilities: string[];
  profile_type: 'student' | 'trainer' | null;
  profile_id: string | null;
}

export interface AdminUser extends User {
  is_staff: boolean;
  /** Whether the *caller* may change this account. Sent by the server so the
   *  screen can show a read-only record rather than a form that cannot save.
   *  It informs the interface; the server enforces the rule again on write. */
  can_administer: boolean;
  last_login: string | null;
  email_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

/** One line of an account's history. */
export interface UserAuditEntry {
  id: string;
  action: string;
  action_label: string;
  result: 'success' | 'failure' | 'denied';
  /** The label rather than a nested user: whoever made the change may since
   *  have been deleted, and the history should still say who it was. */
  actor_label: string;
  created_at: string;
  context: Record<string, unknown>;
}

export interface StudentProfile {
  id: string;
  student_id: string;
  user: User;
  date_of_birth: string | null;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  country: string;
  postal_code: string;
  qualification: Qualification | '';
  institution: string;
  institution_kind: InstitutionKind | '';
  /** For a working professional: what they do there. */
  job_title: string;
  /** An identifier issued elsewhere — a university roll number — that the
   *  student is known by outside this system. */
  roll_number: string;
  graduation_year: number | null;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  emergency_contact_relationship: string;
  guardian_name: string;
  guardian_phone: string;
  fee_status: FeeStatus;
  fee_status_updated_at: string | null;
  /** The fee agreed at registration, in rupees, as the API's decimal string.
   *  `null` is "not decided" — never zero. */
  fee_amount: string | null;
  fee_amount_updated_at: string | null;
  /** The student who referred this one — an id, and a printable label
   *  ("Priya Shah (GRS-S-00012)") so no screen has to fetch the referrer. */
  referred_by: string | null;
  referred_by_label: string | null;
  completion_percent: number;
  is_profile_complete: boolean;
  created_at: string;
  updated_at: string;
  /** Administrator-only fields, absent from a student's own view. */
  notes?: string;
  fee_status_updated_by?: string | null;
  fee_amount_updated_by?: string | null;
  /** How many students this one has referred. Admin view only. */
  referrals_count?: number;
}

export interface StudentListRow {
  id: string;
  student_id: string;
  user_id: string;
  email: string;
  full_name: string;
  city: string;
  qualification: Qualification | '';
  fee_status: FeeStatus;
  fee_amount: string | null;
  institution: string;
  roll_number: string;
  institution_kind: InstitutionKind | '';
  referred_by: string | null;
  is_active: boolean;
  is_email_verified: boolean;
  created_at: string;
}

export interface TrainerProfile {
  id: string;
  trainer_id: string;
  user: User;
  professional_title: string;
  bio: string;
  skills: string[];
  expertise: string;
  qualifications: string;
  years_of_experience: number | null;
  professional_links: Record<string, string>;
  is_accepting_assignments: boolean;
  completion_percent: number;
  is_profile_complete: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrainerListRow {
  id: string;
  trainer_id: string;
  user_id: string;
  email: string;
  full_name: string;
  professional_title: string;
  skills: string[];
  years_of_experience: number | null;
  is_accepting_assignments: boolean;
  is_active: boolean;
  is_email_verified: boolean;
  created_at: string;
}

/** The single error envelope every failing endpoint returns. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
    details?: Record<string, string[] | string> | null;
  };
}

export interface Paginated<T> {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface HealthCheck {
  status: 'ok' | 'error';
  detail: string;
  duration_ms: number;
}

export interface ReadinessResponse {
  status: 'ok' | 'degraded';
  checks: Record<string, HealthCheck>;
}

export interface ApiRoot {
  name: string;
  versions: Record<string, string>;
  health: { live: string; ready: string };
  schema: string;
}

export interface DetailResponse {
  detail: string;
}

// --- Course catalogue -------------------------------------------------------

export type PublishStatus = 'draft' | 'in_review' | 'published' | 'archived';
export type CourseVisibility = 'public' | 'internal' | 'private';
export type CourseDifficulty = 'beginner' | 'intermediate' | 'advanced';
export type LessonContentType = 'text' | 'video' | 'document' | 'external_link';
export type ResourceKind = 'file' | 'link';
export type CourseAuthorRole = 'owner' | 'editor';
export type VideoProvider = 'external_url' | 's3' | 'managed';

export interface Category {
  id: string;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
  position: number;
  course_count: number;
}

export interface CourseListRow {
  id: string;
  code: string;
  slug: string;
  title: string;
  short_description: string;
  category_name: string;
  category_slug: string;
  difficulty: CourseDifficulty;
  estimated_duration_minutes: number | null;
  status: PublishStatus;
  visibility: CourseVisibility;
  thumbnail_url: string | null;
  module_count: number;
  lesson_count: number;
  published_at: string | null;
  created_at: string;
}

/** Video metadata. Never carries the playable URL — see `VideoPlayback`. */
export interface VideoAsset {
  id: string;
  provider: VideoProvider;
  duration_seconds: number | null;
  thumbnail_url: string;
  status: 'pending' | 'processing' | 'ready' | 'failed';
}

/** Returned only by the playback endpoint, after an access check. */
export interface VideoPlayback {
  provider: VideoProvider;
  playback_url: string | null;
  duration_seconds: number | null;
  status: string;
}

export interface LessonResource {
  id: string;
  title: string;
  description: string;
  kind: ResourceKind;
  original_filename: string;
  content_type: string;
  size_bytes: number | null;
  external_url: string;
  position: number;
  is_downloadable: boolean;
  download_url: string | null;
}

/** Navigation entry. Deliberately carries no lesson body. */
export interface LessonSummary {
  id: string;
  title: string;
  slug: string;
  description: string;
  content_type: LessonContentType;
  duration_minutes: number | null;
  position: number;
  status: PublishStatus;
  is_preview: boolean;
  is_required: boolean;
  resource_count: number;
}

export interface LessonContent extends LessonSummary {
  text_content: string;
  external_url: string;
  video: VideoAsset | null;
  resources: LessonResource[];
  module_id: string;
  course_id: string;
}

export interface Module {
  id: string;
  title: string;
  description: string;
  position: number;
  status: PublishStatus;
  is_visible: boolean;
  lessons: LessonSummary[];
}

export interface CourseInstructor {
  full_name: string;
  role: CourseAuthorRole;
}

export interface CourseDetail extends CourseListRow {
  description: string;
  learning_objectives: string[];
  prerequisites: string[];
  content_updated_at: string | null;
  updated_at: string;
  modules: Module[];
  instructors: CourseInstructor[];
  /** Rendering hints from the server. The server still re-checks every call. */
  can_manage: boolean;
  can_publish: boolean;
}

export interface CourseAssignment {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: CourseAuthorRole;
  created_at: string;
}

export interface PublishChecklist {
  ready: boolean;
  blockers: string[];
}

// --- Batches, enrolment and scheduling --------------------------------------

export type BatchStatus = 'upcoming' | 'active' | 'completed' | 'cancelled' | 'archived';
export type EnrollmentStatus =
  | 'pending'
  | 'active'
  | 'suspended'
  | 'completed'
  | 'cancelled';
export type LessonProgressStatus = 'not_started' | 'in_progress' | 'completed';

/** 0 = Monday, matching Python's `date.weekday()`. */
export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export interface BatchSchedule {
  id: string;
  weekday: Weekday;
  weekday_label: string;
  start_time: string;
  end_time: string;
  timezone_name: string;
  location: string;
  trainer_name: string;
  is_active: boolean;
  note: string;
  duration_minutes: number;
}

export interface BatchListRow {
  id: string;
  code: string;
  name: string;
  course_id: string;
  course_code: string;
  course_title: string;
  course_slug: string;
  trainer_name: string;
  start_date: string;
  end_date: string;
  capacity: number;
  enrolled_count: number;
  seats_available: number;
  status: BatchStatus;
  created_at: string;
}

export interface BatchDetail extends BatchListRow {
  description: string;
  trainer_id: string | null;
  trainer_code: string;
  schedules: BatchSchedule[];
  updated_at: string;
  /** Rendering hints from the server, which re-checks every call anyway. */
  can_manage: boolean;
  can_view_roster: boolean;
}

export interface RosterEntry {
  id: string;
  code: string;
  student_id: string;
  student_code: string;
  full_name: string;
  email: string;
  status: EnrollmentStatus;
  enrolled_at: string;
}

export interface Enrollment {
  id: string;
  code: string;
  course_id: string;
  course_code: string;
  course_title: string;
  course_slug: string;
  batch_id: string;
  batch_code: string;
  batch_name: string;
  batch_status: BatchStatus;
  trainer_name: string;
  status: EnrollmentStatus;
  enrolled_at: string;
  start_date: string | null;
  access_end_date: string | null;
  completed_at: string | null;
  grants_access: boolean;
  /** Administrator and trainer views only. */
  student_id?: string;
  student_code?: string;
  student_name?: string;
  student_email?: string;
  status_note?: string;
  status_changed_at?: string | null;
}

export interface LessonProgress {
  id: string;
  lesson_id: string;
  lesson_title: string;
  status: LessonProgressStatus;
  first_accessed_at: string;
  last_accessed_at: string;
  completed_at: string | null;
}

export interface CourseProgress {
  total_lessons: number;
  completed_lessons: number;
  percent: number;
  last_lesson_id: string | null;
  last_lesson_title: string | null;
  last_accessed_at: string | null;
  lessons?: LessonProgress[];
}

export type CalendarEventKind =
  | 'class'
  | 'batch_start'
  | 'batch_end'
  | 'course_start'
  | 'course_end'
  | 'assignment_due'
  // Emitted by `apps.dashboards.calendar` and missing here until now, which is
  // the failure mode of a hand-written union: the backend adds a source, the
  // type says it cannot happen, and the screen silently renders a project
  // deadline as whatever its fallback branch does.
  | 'project_due'
  | 'quiz'
  | 'exam'
  | 'announcement';

export interface CalendarEvent {
  kind: CalendarEventKind;
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  location: string;
  batch_id: string | null;
  batch_code: string;
  course_id: string | null;
  course_title: string;
  trainer_name: string;
  metadata: Record<string, string>;
}

export interface CalendarResponse {
  start: string;
  end: string;
  count: number;
  events: CalendarEvent[];
}

export interface DashboardCourse {
  enrollment_id: string;
  course_id: string;
  course_title: string;
  course_slug: string;
  batch_code: string;
  batch_name: string;
  status: EnrollmentStatus;
  grants_access: boolean;
  progress_percent: number;
  completed_lessons: number;
  total_lessons: number;
  last_lesson_id: string | null;
  last_lesson_title: string | null;
}

export interface DashboardBatch {
  id: string;
  code: string;
  name: string;
  course_title: string;
  status: BatchStatus;
  enrollment_status?: EnrollmentStatus;
  start_date: string;
  end_date: string;
  capacity?: number;
  enrolled_count?: number;
}

export interface StudentDashboard {
  is_student: boolean;
  courses: DashboardCourse[];
  batches: DashboardBatch[];
  upcoming_classes: CalendarEvent[];
  continue_learning: DashboardCourse | null;
  recent_activity: { kind: string; title: string; at: string; status: string }[];
  notifications: { title?: string; body?: string }[];
}

export interface TrainerDashboard {
  is_trainer: boolean;
  batches: DashboardBatch[];
  today_classes: CalendarEvent[];
  upcoming_classes: CalendarEvent[];
  student_count: number;
  courses: { course_id: string; title: string; slug: string; batch_count: number }[];
}

// ---------------------------------------------------------------------------
// Phase 4 — class sessions, attendance, assignments, assessments, rules
// ---------------------------------------------------------------------------

export type SessionStatus =
  | 'scheduled'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'rescheduled';

export interface ClassSession {
  id: string;
  batch_id: string;
  batch_code: string;
  batch_name: string;
  course_title: string;
  session_date: string;
  start_time: string;
  end_time: string;
  timezone_name: string;
  starts_at: string;
  ends_at: string;
  duration_minutes: number;
  trainer_name: string;
  /** What the trainer wrote, in their own words. */
  topic: string;
  location: string;
  status: SessionStatus;
  cancellation_reason: string;
  attendance_taken_at: string | null;
  can_take_attendance: boolean;
  /**
   * The curriculum this class was meant to cover, and what it actually did.
   *
   * Both nullable: a class can be held without a plan, and one that has not
   * happened yet has no actual. They are what makes "is this batch ahead or
   * behind?" answerable — `topic` above is the human note and cannot be
   * compared against anything.
   */
  planned_lesson_id: string | null;
  planned_lesson_title: string | null;
  actual_lesson_id: string | null;
  actual_lesson_title: string | null;
  topic_status: TopicStatus;
}

/** Where a class sits against the plan. Mirrors `apps.sessions.models.TopicStatus`. */
export type TopicStatus =
  | 'planned'
  | 'in_progress'
  | 'completed'
  | 'skipped'
  | 'rescheduled';

export type AttendanceStatus = 'present' | 'absent' | 'late' | 'excused';

export interface RegisterEntry {
  enrollment_id: string;
  student_code: string;
  full_name: string;
  enrollment_status: EnrollmentStatus;
  status: AttendanceStatus | null;
  note: string;
  was_corrected: boolean;
}

export interface Register {
  session_id: string;
  session_date: string;
  batch_code: string;
  can_mark: boolean;
  attendance_taken_at: string | null;
  entries: RegisterEntry[];
}

export interface MarkResult {
  created: number;
  updated: number;
  corrections: number;
}

export interface AttendanceRecord {
  id: string;
  session_id: string;
  session_date: string;
  start_time: string;
  topic: string;
  batch_code: string;
  status: AttendanceStatus;
  note: string;
  was_corrected: boolean;
  marked_at: string;
}

/** Counts plus the requirement from the academic configuration (§4.7). */
export interface AttendanceSummary {
  total_sessions: number;
  present: number;
  late: number;
  absent: number;
  excused: number;
  attended: number;
  percentage: number | null;
  required: boolean;
  minimum_percent: string;
  met: boolean | null;
}

export interface MyAttendance {
  enrollment_id: string;
  course_title: string;
  batch_code: string;
  summary: AttendanceSummary;
  records: AttendanceRecord[];
}

export type AcademicLifecycle = 'draft' | 'published' | 'closed' | 'archived';
export type SubmissionKind = 'file' | 'text' | 'link' | 'any';
export type SubmissionStatus = 'submitted' | 'graded' | 'returned';

export interface AssignmentAttachment {
  id: string;
  title: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface SubmissionFile {
  id: string;
  original_filename: string;
  extension: string;
  size_bytes: number;
  checksum: string;
  created_at: string;
}

export interface Submission {
  id: string;
  assignment: string;
  assignment_code: string;
  assignment_title: string;
  attempt: number;
  status: SubmissionStatus;
  text_answer: string;
  link_url: string;
  submitted_at: string;
  is_late: boolean;
  marks_awarded: string | null;
  max_marks: string;
  is_passing: boolean | null;
  feedback: string;
  graded_at: string | null;
  files: SubmissionFile[];
  created_at: string;
}

export interface StaffSubmission extends Submission {
  enrollment: string;
  student_id: string;
  student_name: string;
  batch_code: string;
  graded_by_name: string | null;
}

export interface Assignment {
  id: string;
  code: string;
  course: string;
  course_title: string;
  module: string | null;
  module_title: string | null;
  lesson: string | null;
  lesson_title: string | null;
  batch: string | null;
  batch_code: string | null;
  title: string;
  instructions: string;
  submission_kind: SubmissionKind;
  max_marks: string;
  passing_marks: string | null;
  due_at: string | null;
  allow_late: boolean;
  late_cutoff_at: string | null;
  allow_resubmission: boolean;
  max_attempts: number;
  status: AcademicLifecycle;
  published_at: string | null;
  is_open: boolean;
  attachments: AssignmentAttachment[];
  submission_count: number;
  created_at: string;
  updated_at: string;
}

export interface StudentAssignment {
  id: string;
  code: string;
  course: string;
  course_title: string;
  module: string | null;
  lesson: string | null;
  title: string;
  instructions: string;
  submission_kind: SubmissionKind;
  max_marks: string;
  passing_marks: string | null;
  due_at: string | null;
  allow_late: boolean;
  late_cutoff_at: string | null;
  allow_resubmission: boolean;
  max_attempts: number;
  status: AcademicLifecycle;
  is_open: boolean;
  attachments: AssignmentAttachment[];
  my_submission: Submission | null;
}

export type AssessmentCategory = 'weekly_test' | 'practice' | 'mock' | 'other';
export type AssessmentDelivery = 'external_link' | 'file_upload' | 'offline';
export type ResultSource = 'manual' | 'import' | 'graded';

export interface Assessment {
  id: string;
  code: string;
  batch: string;
  batch_code: string;
  course: string;
  course_title: string;
  module: string | null;
  title: string;
  description: string;
  category: AssessmentCategory;
  delivery: AssessmentDelivery;
  external_url: string;
  external_provider: string;
  backing_assignment: string | null;
  scheduled_for: string | null;
  duration_minutes: number | null;
  opens_at: string | null;
  closes_at: string | null;
  max_marks: string;
  passing_marks: string | null;
  status: AcademicLifecycle;
  published_at: string | null;
  is_open: boolean;
  result_count: number;
  created_at: string;
  updated_at: string;
}

export interface AssessmentResult {
  id: string;
  assessment: string;
  assessment_code: string;
  assessment_title: string;
  marks_obtained: string | null;
  max_marks: string;
  is_absent: boolean;
  is_passing: boolean | null;
  percentage: number | null;
  remarks: string;
  recorded_at: string;
}

export interface StudentAssessment extends Omit<Assessment, 'result_count'> {
  my_result: AssessmentResult | null;
}

export interface MarksSheetEntry {
  enrollment_id: string;
  student_code: string;
  student_name: string;
  marks_obtained: string | null;
  is_absent: boolean;
  remarks: string;
  source: ResultSource | '';
}

export interface MarksSheet {
  assessment: Assessment;
  entries: MarksSheetEntry[];
  can_record: boolean;
}

export type ImportStatus = 'preview' | 'confirmed' | 'rejected' | 'failed';

export interface ImportProblem {
  line: number;
  student_id: string;
  problem: string;
}

export interface ImportRow {
  line: number;
  student_id: string;
  enrollment_id: string;
  student_name: string;
  marks: string | null;
  is_absent: boolean;
  remarks: string;
  replaces_existing: boolean;
}

export interface ImportReport {
  columns: Record<string, string>;
  rows: ImportRow[];
  errors: ImportProblem[];
  not_in_file: { student_id: string; student_name: string }[];
  summary: {
    read: number;
    valid: number;
    errors: number;
    would_create: number;
    would_update: number;
    cohort_size: number;
    not_in_file: number;
  };
}

export interface ResultImport {
  id: string;
  assessment: string;
  original_filename: string;
  checksum: string;
  row_count: number;
  valid_count: number;
  error_count: number;
  created_count: number;
  updated_count: number;
  status: ImportStatus;
  report: ImportReport;
  confirmed_at: string | null;
  created_at: string;
}

/** The rules in force, after course → institution → code default. */
export interface EffectivePolicy {
  minimum_attendance_percent: string;
  attendance_required_for_completion: boolean;
  passing_percent: string;
  assignment_default_max_marks: string;
  assignment_allow_late: boolean;
  assignment_default_max_attempts: number;
  assignment_required_for_completion: boolean;
  minimum_assignment_completion_percent: string;
  test_default_max_marks: string;
  tests_required_for_completion: boolean;
  minimum_test_average_percent: string;
  minimum_lesson_completion_percent: string;
}

/** A stored policy row. `null` on a field means "inherit". */
export interface AcademicPolicy {
  id: string;
  scope: 'global' | 'course';
  course: string | null;
  course_title: string | null;
  minimum_attendance_percent: string | null;
  attendance_required_for_completion: boolean | null;
  passing_percent: string | null;
  assignment_default_max_marks: string | null;
  assignment_allow_late: boolean | null;
  assignment_default_max_attempts: number | null;
  assignment_required_for_completion: boolean | null;
  minimum_assignment_completion_percent: string | null;
  test_default_max_marks: string | null;
  tests_required_for_completion: boolean | null;
  minimum_test_average_percent: string | null;
  minimum_lesson_completion_percent: string | null;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Phase 5 — projects, question bank, examinations
// ---------------------------------------------------------------------------

export type ProjectKind = 'small' | 'major' | 'capstone';

export type ProjectWorkStatus =
  | 'assigned'
  | 'in_progress'
  | 'submitted'
  | 'under_review'
  | 'rework'
  | 'approved'
  | 'completed';

export interface RubricCriterion {
  key: string;
  label: string;
  max_marks: string;
}

export interface ProjectFile {
  id: string;
  original_filename: string;
  extension: string;
  size_bytes: number;
  checksum: string;
  created_at: string;
}

export interface StudentProjectWork {
  id: string;
  project: string;
  project_code: string;
  project_title: string;
  status: ProjectWorkStatus;
  repository_url: string;
  deployment_url: string;
  notes: string;
  submitted_at: string | null;
  submission_count: number;
  is_late: boolean;
  marks_awarded: string | null;
  max_marks: string;
  rubric_scores: Record<string, string>;
  is_passing: boolean | null;
  is_open_to_student: boolean;
  feedback: string;
  reviewed_at: string | null;
  files: ProjectFile[];
  created_at: string;
}

export interface ReviewerProjectWork extends StudentProjectWork {
  enrollment: string;
  student_id: string;
  student_name: string;
  batch_code: string;
  reviewer_name: string | null;
}

export interface Project {
  id: string;
  code: string;
  course: string;
  course_title: string;
  module: string | null;
  module_title: string | null;
  batch: string | null;
  batch_code: string | null;
  title: string;
  description: string;
  instructions: string;
  deliverables: string;
  kind: ProjectKind;
  is_required: boolean;
  start_date: string | null;
  end_date: string | null;
  requires_repository_url: boolean;
  requires_deployment_url: boolean;
  max_marks: string;
  passing_marks: string | null;
  rubric: RubricCriterion[];
  reviewer: string | null;
  reviewer_name: string | null;
  status: AcademicLifecycle;
  published_at: string | null;
  is_open: boolean;
  assigned_count: number;
  created_at: string;
  updated_at: string;
}

export interface StudentProject extends Project {
  my_work: StudentProjectWork | null;
}

export interface RequiredProjectProgress {
  enrollment_id: string;
  course_title: string;
  batch_code: string;
  required: number;
  finished: number;
  met: boolean;
  outstanding: { id: string; code: string; title: string }[];
}

export type QuestionType =
  | 'mcq'
  | 'multiple'
  | 'true_false'
  | 'short_answer'
  | 'long_answer'
  | 'file';

export type Difficulty = 'easy' | 'medium' | 'hard';

export interface QuestionOption {
  id: string;
  text: string;
  is_correct: boolean;
  position: number;
}

export interface Question {
  id: string;
  course: string | null;
  course_title: string | null;
  module: string | null;
  question_type: QuestionType;
  text: string;
  difficulty: Difficulty;
  marks: string;
  negative_marks: string;
  tags: string[];
  answer_key: string[];
  explanation: string;
  is_active: boolean;
  is_auto_graded: boolean;
  options: QuestionOption[];
  created_at: string;
  updated_at: string;
}

export interface ExamSection {
  id: string;
  title: string;
  position: number;
  question_count: number;
  difficulty: string;
  question_type: string;
  tags: string[];
}

export interface Exam {
  id: string;
  code: string;
  batch: string;
  batch_code: string;
  course: string;
  course_title: string;
  title: string;
  description: string;
  instructions: string;
  opens_at: string | null;
  closes_at: string | null;
  duration_minutes: number;
  max_attempts: number;
  passing_marks: string | null;
  negative_marking: boolean;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  results_published: boolean;
  results_published_at: string | null;
  status: AcademicLifecycle;
  published_at: string | null;
  is_open: boolean;
  total_questions: number;
  attempt_count: number;
  sections: ExamSection[];
  created_at: string;
  updated_at: string;
}

export interface ExamReadiness {
  ready: boolean;
  problems: string[];
  sections: number;
  questions: number;
  approximate_total_marks: string;
}

export type AttemptStatus = 'in_progress' | 'submitted' | 'graded' | 'expired';

export interface ExamAttempt {
  id: string;
  exam: string;
  exam_code: string;
  exam_title: string;
  attempt_number: number;
  status: AttemptStatus;
  started_at: string;
  expires_at: string;
  submitted_at: string | null;
  seconds_remaining: number;
  results_published: boolean;
}

/** A question as the candidate sees it. Carries no answer, by construction. */
export interface CandidateQuestion {
  id: string;
  position: number;
  section: string | null;
  question_type: QuestionType;
  text: string;
  marks: string;
  negative_marks: string;
  options: { id: string; text: string }[];
  selected_options: string[];
  text_answer: string;
  answered_filename: string;
}

export interface AttemptPaper {
  attempt: ExamAttempt;
  questions: CandidateQuestion[];
}

export interface AttemptResult {
  id: string;
  exam: string;
  exam_code: string;
  exam_title: string;
  attempt_number: number;
  status: AttemptStatus;
  submitted_at: string | null;
  graded_at: string | null;
  total_score: string | null;
  max_score: string | null;
  is_passing: boolean | null;
  percentage: number | null;
  results_published: boolean;
}

export interface StaffAttempt extends AttemptResult {
  enrollment: string;
  student_id: string;
  student_name: string;
  batch_code: string;
  auto_score: string;
  manual_score: string;
  needs_manual_marking: boolean;
  started_at: string;
  expires_at: string;
}

export interface MarkableAnswer {
  id: string;
  attempt: string;
  position: number;
  question_text: string;
  question_type: QuestionType;
  marks: string;
  text_answer: string;
  answered_filename: string;
  awarded: string | null;
  marker_feedback: string;
  student_id: string;
  student_name: string;
}

export interface ReviewedQuestion {
  position: number;
  question_text: string;
  question_type: QuestionType;
  marks: string;
  awarded: string | null;
  is_correct: boolean | null;
  explanation: string;
  marker_feedback: string;
}

export interface AttemptReview {
  attempt: AttemptResult;
  questions: ReviewedQuestion[];
}

// ---------------------------------------------------------------------------
// Phase 6 — progress, completion, certificates
// ---------------------------------------------------------------------------

export type DeliveryMode = 'offline' | 'online' | 'hybrid';

export type CompletionStatus = 'in_progress' | 'eligible' | 'approved' | 'rejected';

export interface LessonProgressSummary {
  total: number;
  started: number;
  completed: number;
  percent: number;
  last_lesson_id: string | null;
  last_lesson_title: string | null;
  last_accessed_at: string | null;
  completed_at: string | null;
}

export interface ModuleProgress {
  id: string;
  title: string;
  position: number;
  total_lessons: number;
  completed_lessons: number;
  percent: number;
  is_complete: boolean;
}

export interface AttendanceProgress {
  total: number;
  attended: number;
  percent: number;
  has_records: boolean;
  present: number;
  late: number;
  absent: number;
  excused: number;
}

export interface AssignmentProgress {
  total: number;
  submitted: number;
  graded: number;
  passed: number;
  percent: number;
}

export interface TestProgress {
  total: number;
  recorded: number;
  percent: number;
  average_percent: number | null;
  passed: number;
}

export interface ProjectProgress {
  required: number;
  finished: number;
  percent: number;
  outstanding: { id: string; code: string; title: string }[];
}

export interface ExamProgressSummary {
  exists: boolean;
  sat: boolean;
  passed: boolean | null;
  best_percent: number | null;
}

/** The one progress shape. No screen computes its own (§6.3). */
export interface ProgressReport {
  enrollment_id: string;
  course_title: string;
  batch_code: string;
  delivery_mode: DeliveryMode;
  lessons: LessonProgressSummary;
  modules: ModuleProgress[];
  attendance: AttendanceProgress;
  assignments: AssignmentProgress;
  tests: TestProgress;
  projects: ProjectProgress;
  exam: ExamProgressSummary;
}

export interface RuleOutcome {
  key: string;
  label: string;
  required: boolean;
  met: boolean;
  detail: string;
  numbers: Record<string, unknown>;
}

export interface CourseCompletion {
  id: string;
  enrollment: string;
  student_name?: string;
  student_code?: string;
  course_title: string;
  batch_code: string;
  status: CompletionStatus;
  became_eligible_at: string | null;
  completed_on: string | null;
  decision_note?: string;
  decided_at?: string | null;
  decided_by_name?: string | null;
  rule_snapshot?: {
    evaluated_at: string;
    eligible: boolean;
    overridden: boolean;
    rules: RuleOutcome[];
  };
  updated_at?: string;
}

export interface CompletionEvaluation {
  progress: ProgressReport;
  eligible: boolean;
  rules: RuleOutcome[];
  unmet: string[];
  required_count: number;
  met_count: number;
  completion: CourseCompletion | null;
}

export type CertificateStatus = 'issued' | 'revoked' | 'superseded';

export interface CertificateTemplate {
  id: string;
  name: string;
  is_default: boolean;
  institution_name: string;
  title: string;
  body: string;
  signatory_name: string;
  signatory_title: string;
  footer: string;
  created_at: string;
  updated_at: string;
}

export interface Certificate {
  id: string;
  number: string;
  verification_code: string;
  completion?: string;
  template?: string | null;
  template_name?: string | null;
  student_name?: string;
  student_code?: string;
  course_title: string;
  batch_code: string;
  completion_date: string;
  status: CertificateStatus;
  is_live: boolean;
  issued_at: string;
  issued_by_name?: string | null;
  revoked_at?: string | null;
  revocation_reason?: string;
  supersedes_number?: string | null;
  reissue_reason?: string;
}

/** §6.8 — every field the public verification endpoint returns, and no others. */
export interface PublicCertificate {
  certificate_number: string;
  student_name: string;
  course_title: string;
  completion_date: string;
  issued_on: string;
  status: CertificateStatus;
  is_valid: boolean;
  revoked_on: string | null;
  institution: string;
}

// ---------------------------------------------------------------------------
// Phase 7 — notifications, announcements, discussions, learning surface
// ---------------------------------------------------------------------------

export type NotificationCategory =
  | 'academic'
  | 'schedule'
  | 'announcements'
  | 'administrative';

export interface AppNotification {
  id: string;
  kind: string;
  category: NotificationCategory;
  title: string;
  body: string;
  link_path: string;
  resource_type: string;
  resource_id: string;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPreference {
  email_academic: boolean;
  email_schedule: boolean;
  email_announcements: boolean;
  email_administrative: boolean;
  updated_at: string;
}

export type Audience = 'everyone' | 'course' | 'batch' | 'selected';
export type AnnouncementStatus = 'draft' | 'published' | 'archived';

export interface Announcement {
  id: string;
  title: string;
  body: string;
  audience?: Audience;
  course?: string | null;
  course_title: string | null;
  batch?: string | null;
  batch_code: string | null;
  is_pinned: boolean;
  status?: AnnouncementStatus;
  published_at: string | null;
  expires_at: string | null;
  is_live?: boolean;
  created_by_name: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface DiscussionThread {
  id: string;
  batch: string;
  batch_code: string;
  course_title: string;
  title: string;
  body: string;
  author_name: string;
  is_pinned: boolean;
  is_closed: boolean;
  reply_count: number;
  last_reply_at: string | null;
  has_trainer_reply: boolean;
  created_at: string;
}

export interface DiscussionReply {
  id: string;
  thread: string;
  author_name: string;
  body: string;
  is_trainer_response: boolean;
  is_hidden: boolean;
  hidden_reason: string;
  hidden_by_name: string | null;
  created_at: string;
}

export interface DiscussionThreadDetail extends DiscussionThread {
  replies: DiscussionReply[];
  can_reply: boolean;
  can_moderate: boolean;
}

export interface LessonRef {
  lesson_id: string;
  lesson_title: string;
  module_title: string;
  course_slug: string;
  last_accessed_at: string | null;
}

export interface RecentLesson extends LessonRef {
  status: LessonProgressStatus;
}

export interface LearningHome {
  enrollment_id: string;
  course_title: string;
  course_slug: string;
  batch_code: string;
  continue_learning: LessonRef | null;
  recent: RecentLesson[];
}

export interface UpcomingItem {
  kind: string;
  title: string;
  start: string;
  course_title: string;
  batch_code: string;
  metadata: Record<string, unknown>;
}

export interface Bookmark {
  id: string;
  lesson: string;
  lesson_title: string;
  module_title: string;
  course_slug: string;
  note: string;
  created_at: string;
}

export interface LessonNote {
  id: string;
  lesson: string;
  lesson_title: string;
  module_title: string;
  course_slug: string;
  body: string;
  updated_at: string;
}

export interface Peer {
  full_name: string;
  student_code: string;
  is_you: boolean;
}

// ---------------------------------------------------------------------------
// Phase 8 — reports, analytics, dashboards, data tools
// ---------------------------------------------------------------------------

export interface ReportColumn {
  key: string;
  label: string;
}

export interface ReportDefinition {
  key: string;
  label: string;
  description: string;
  source: string;
  columns: ReportColumn[];
}

export interface ReportPage {
  key: string;
  label: string;
  description: string;
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
}

/** A number and the definition §8.6 requires it to carry. */
export interface LmsMetric {
  key: string;
  label: string;
  definition: string;
  unit: 'percent' | 'count';
  value: number | null;
  numerator?: number | null;
  denominator?: number | null;
}

export interface TrendPoint {
  week: string;
  counted: number;
  attended: number;
  percent: number | null;
}

export interface AdminDashboard {
  active_students: number;
  active_trainers: number;
  published_courses: number;
  active_batches: number;
  awaiting_completion_approval: number;
  certificates_issued: number;
  metrics: LmsMetric[];
}

export interface TrainerWorkload {
  batches: number;
  sessions_today: number;
  registers_outstanding: number;
  submissions_to_mark: number;
  exam_answers_to_mark: number;
  projects_to_review: number;
  upcoming_tests: number;
  upcoming_exams: number;
}

export interface BatchSummary {
  id: string;
  code: string;
  name: string;
  course_title: string;
  status: BatchStatus;
  students: number;
  attendance_percent: number | null;
}

export type BulkImportKind = 'students' | 'attendance';
export type BulkImportStatus = 'preview' | 'confirmed' | 'rejected' | 'failed';

export interface BulkImportReport {
  columns: Record<string, string>;
  rows: Record<string, unknown>[];
  errors: { line: number; problem: string; email?: string; student_id?: string }[];
  not_in_file?: { student_id: string; student_name: string }[];
  summary: {
    read: number;
    valid: number;
    errors: number;
    would_create: number;
    would_update: number;
  };
}

export interface BulkImport {
  id: string;
  kind: BulkImportKind;
  original_filename: string;
  checksum: string;
  row_count: number;
  valid_count: number;
  error_count: number;
  created_count: number;
  updated_count: number;
  status: BulkImportStatus;
  report: BulkImportReport;
  confirmed_at: string | null;
  created_at: string;
}

export type AcademicEventKind = 'term' | 'holiday' | 'exam_week' | 'other';

export interface AcademicEvent {
  id: string;
  name: string;
  kind: AcademicEventKind;
  start_date: string;
  end_date: string;
  note: string;
  created_at: string;
}

export interface GradeBand {
  label: string;
  min_percent: string;
}
