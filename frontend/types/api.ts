/**
 * Types mirroring the backend API contract (see backend/config/api_urls.py and
 * the OpenAPI schema at /api/schema/).
 *
 * Hand-written and deliberately narrow: only what the frontend consumes. Once
 * the surface grows further, generate this file from the OpenAPI document so
 * the two cannot drift.
 */

export type UserRole = 'admin' | 'trainer' | 'student';

export type FeeStatus = 'pending' | 'partial' | 'paid' | 'waived' | 'overdue';

export type Qualification =
  | 'secondary'
  | 'higher_secondary'
  | 'diploma'
  | 'bachelors'
  | 'masters'
  | 'other';

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
  last_login: string | null;
  email_verified_at: string | null;
  created_at: string;
  updated_at: string;
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
  graduation_year: number | null;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  emergency_contact_relationship: string;
  guardian_name: string;
  guardian_phone: string;
  fee_status: FeeStatus;
  fee_status_updated_at: string | null;
  completion_percent: number;
  is_profile_complete: boolean;
  created_at: string;
  updated_at: string;
  /** Administrator-only fields, absent from a student's own view. */
  notes?: string;
  fee_status_updated_by?: string | null;
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
