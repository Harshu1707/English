const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "verba_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export const TOKEN_STORAGE_KEY = TOKEN_KEY;
// Fired when the API rejects a stored token (expired/invalid) so the app can sign the user out.
export const UNAUTHORIZED_EVENT = "verba:unauthorized";
export const EXPIRED_FLAG = "verba_session_expired"; // read once by /login to explain why the user landed there

const FIELD_LABELS: Record<string, string> = {
  email: "Email",
  full_name: "Name",
  password: "Password",
  confirm_password: "Confirm password",
  role: "Role",
  admin_invite_code: "Admin invite code",
};

// FastAPI returns `detail` as a string for our own errors and as a list of objects for validation errors.
function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item: { loc?: unknown[]; msg?: string }) => {
        const msg = (item.msg || "Invalid value").replace(/^Value error, /, "");
        const field = String(item.loc?.[item.loc.length - 1] ?? "");
        const label = FIELD_LABELS[field];
        return label ? `${label}: ${msg}` : msg;
      })
      .join(". ");
  }
  return fallback;
}

async function request(path: string, init: RequestInit = {}) {
  const isCredentialCall = path === "/auth/login" || path === "/auth/register";
  const token = isCredentialCall ? null : getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new Error("We can't reach the Verba server right now. Check your connection and try again.");
  }
  if (res.status === 401 && token) {
    // The stored token was rejected (expired, tampered, or the account was deactivated).
    clearToken();
    if (typeof window !== "undefined") {
      try { window.sessionStorage.setItem(EXPIRED_FLAG, "1"); } catch { /* storage unavailable */ }
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
  }
  if (!res.ok) {
    let detail = res.statusText || "Something went wrong. Please try again.";
    try {
      const body = await res.json();
      detail = formatDetail(body.detail, detail);
    } catch {
      /* no JSON body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export type LessonMedia = {
  id: number;
  lesson_id: number;
  url: string;
  media_type: string;
  provider: string;
  public_id: string | null;
  resource_type: string | null;
  format: string | null;
  width: number | null;
  height: number | null;
  file_size: number | null;
  duration_seconds: number | null;
  original_filename: string | null;
};

export const mediaApi = {
  list: (lessonId: number): Promise<LessonMedia[]> => request(`/admin/media/lesson/${lessonId}`),

  upload: (lessonId: number, mediaType: string, file: File): Promise<LessonMedia> => {
    const body = new FormData();
    body.append("file", file);
    return request(`/admin/media/lesson/${lessonId}?media_type=${encodeURIComponent(mediaType)}`, {
      method: "POST",
      body,
    });
  },

  replace: (mediaId: number, file: File): Promise<LessonMedia> => {
    const body = new FormData();
    body.append("file", file);
    return request(`/admin/media/${mediaId}`, { method: "PUT", body });
  },

  remove: (mediaId: number): Promise<null> => request(`/admin/media/${mediaId}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Admin analytics: real, database-driven statistics for the admin dashboard
// ---------------------------------------------------------------------------
export type AdminUserStats = {
  total_users: number;
  total_teachers: number;
  total_admins: number;
  active_users: number;
  inactive_users: number;
  users_logged_in: number;
  users_never_logged_in: number;
  new_users_last_7_days: number;
  new_users_last_30_days: number;
};

export type DailyLoginPoint = { date: string; count: number };

export type AdminLoginStats = {
  today: number;
  yesterday: number;
  last_7_days: number;
  last_30_days: number;
  daily_history: DailyLoginPoint[];
};

export type AdminCompletionStats = {
  users_started_learning: number;
  users_completed_a_lesson: number;
  lessons_completed_total: number;
  users_completed_practice: number;
  practice_attempts_completed: number;
  practice_attempts_total: number;
  total_published_lessons: number;
  completion_rate_percent: number | null;
};

export type TopMediaItem = { lesson_id: number; lesson_title: string; media_type: string; times_accessed: number };

export type AdminMediaStats = {
  total_media: number;
  total_videos: number;
  total_audio: number;
  total_images: number;
  lessons_with_media: number;
  users_who_accessed_media: number;
  video_activity_count: number;
  podcast_activity_count: number;
  most_used_media: TopMediaItem[];
};

export type RecentActivityItem = {
  user_name: string;
  activity: string;
  detail: string;
  score: number | null;
  created_at: string;
};

export type AdminOverview = {
  users: AdminUserStats;
  logins: AdminLoginStats;
  completion: AdminCompletionStats;
  media: AdminMediaStats;
  recent_activity: RecentActivityItem[];
};

export const adminApi = {
  overview: (): Promise<AdminOverview> => request("/admin/stats/overview"),
};

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------
export type Role = "admin" | "teacher";
export type User = { id: number; email: string; full_name: string; role: Role };
export type AuthResponse = { access_token: string; token_type: string; user: User | null };

export type RegisterInput = {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
  role: Role;
  admin_invite_code?: string;
};

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const authApi = {
  register: (input: RegisterInput): Promise<AuthResponse> => request("/auth/register", jsonInit("POST", input)),
  login: (email: string, password: string): Promise<AuthResponse> =>
    request("/auth/login", jsonInit("POST", { email, password })),
  me: (): Promise<User> => request("/auth/me"),
};

// ---------------------------------------------------------------------------
// Practice: recording upload + speaking analysis
// ---------------------------------------------------------------------------
export type AttemptStatus = "pending" | "processing" | "transcribing" | "analyzing" | "completed" | "failed";

export type AttemptSummary = {
  id: number;
  number: number | null;
  status: AttemptStatus;
  overall_score: number | null;
  lesson_id: number | null;
  duration_seconds: number | null;
  created_at: string;
};

export type GrammarError = { original: string; correction: string; explanation: string; category: string | null };
export type VocabSuggestion = { word: string; suggestion: string; note: string };
export type PronunciationIssue = { word: string; note: string };
export type FillerWord = { word: string; count: number };

export type AttemptDetail = AttemptSummary & {
  reference_text: string;
  transcript: string | null;
  audio_url: string;
  error_message: string | null;
  scores: {
    overall: number | null;
    pronunciation: number | null;
    fluency: number | null;
    grammar: number | null;
    vocabulary: number | null;
    sentence_structure: number | null;
    pace: number | null;
  };
  words_per_minute: number | null;
  filler_words: FillerWord[];
  pronunciation_issues: PronunciationIssue[];
  grammar_errors: GrammarError[];
  vocabulary_suggestions: VocabSuggestion[];
  repeated_words: string[];
  sentence_structure_notes: string[];
  strengths: string[];
  areas_to_improve: string[];
  practice_words: string[];
  recommendations: string[];
  overall_feedback: string | null;
  assessment: Record<string, string>;
};

export const ACTIVE_STATUSES: AttemptStatus[] = ["pending", "processing", "transcribing", "analyzing"];

export const practiceApi = {
  createAttempt: (
    file: Blob,
    opts: { filename: string; referenceText: string; durationSeconds?: number },
  ): Promise<AttemptSummary> => {
    const body = new FormData();
    body.append("file", file, opts.filename);
    body.append("reference_text", opts.referenceText);
    if (opts.durationSeconds) body.append("duration_seconds", String(Math.round(opts.durationSeconds * 10) / 10));
    return request("/practice/attempts", { method: "POST", body });
  },
  getAttempt: (id: number): Promise<AttemptDetail> => request(`/practice/attempts/${id}`),
  listAttempts: (limit = 20, offset = 0): Promise<{ total: number; items: AttemptSummary[] }> =>
    request(`/practice/attempts?limit=${limit}&offset=${offset}`),
  retry: (id: number): Promise<AttemptSummary> => request(`/practice/attempts/${id}/retry`, { method: "POST" }),
};

// ---------------------------------------------------------------------------
// Progress: streak, learning statistics and the activity calendar
// ---------------------------------------------------------------------------
export type ProgressSummary = {
  today: string; // YYYY-MM-DD in the application's timezone
  current_streak: number;
  longest_streak: number;
  active_days: number;
  progress_percent: number;
  completed_videos: number;
  completed_podcasts: number;
  practice_activities: number;
  lessons_completed: number;
  lessons_total: number;
  speaking_attempts: number;
  speaking_seconds: number;
  overall_score: number | null;
  average_score: number | null;
  signals: {
    pronunciation: number | null;
    fluency: number | null;
    grammar: number | null;
    vocabulary: number | null;
  };
};

export type ActivityCalendar = {
  year: number;
  month: number; // 1-12
  days_in_month: number;
  first_weekday: number; // Monday = 0 ... Sunday = 6
  today: string;
  active_days: number[];
};

export type ActivityType = "video" | "podcast" | "practice";

/** Fired after any qualifying activity so the streak/calendar refetch themselves. */
export const ACTIVITY_EVENT = "verba:activity-changed";
export function notifyActivity() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(ACTIVITY_EVENT));
}

export const progressApi = {
  summary: (): Promise<ProgressSummary> => request("/progress/summary"),
  calendar: (year?: number, month?: number): Promise<ActivityCalendar> =>
    request(year && month ? `/progress/calendar?year=${year}&month=${month}` : "/progress/calendar"),
  logActivity: (activity_type: Exclude<ActivityType, "practice">, lesson_id?: number): Promise<ProgressSummary> =>
    request("/progress/activity", jsonInit("POST", lesson_id ? { activity_type, lesson_id } : { activity_type })),
  /**
   * For a video/audio player: report how far the teacher is (0-100). The server marks the lesson
   * completed once, with the time, when the value first reaches its completion threshold (90%).
   */
  reportLessonProgress: (lessonId: number, percent: number): Promise<LessonProgress> =>
    request(`/progress/lessons/${lessonId}`, jsonInit("POST", { percent: Math.max(0, Math.min(100, Math.round(percent))) })),
};

export type LessonProgress = {
  lesson_id: number;
  progress_percent: number;
  completed: boolean;
  completed_at: string | null;
};

// ---------------------------------------------------------------------------
// Admin: content completion (which teachers finished which videos / podcasts)
// ---------------------------------------------------------------------------
export type ContentKind = "video" | "podcast";
export type CompletionStatus = "completed" | "not_completed";

export type ContentProgressSummary = {
  total_teachers: number;
  total_videos: number;
  total_podcasts: number;
  video_completions: number;
  podcast_completions: number;
  possible_video_completions: number;
  possible_podcast_completions: number;
  teachers_completed_videos: number;
  teachers_completed_podcasts: number;
};

export type ContentProgressTeacher = {
  teacher_id: number;
  name: string;
  email: string;
  videos_completed: number;
  podcasts_completed: number;
  total_completed: number;
  last_activity: string | null;
};

export type ContentProgressItem = {
  content_id: number;
  title: string;
  content_type: ContentKind;
  published: boolean;
  completed_count: number;
  not_completed_count: number;
  total_teachers: number;
};

export type ContentProgressPerson = {
  teacher_id: number;
  name: string;
  email: string;
  progress_percent: number;
  completed_at: string | null;
};

export type ContentProgressDetail = {
  content_id: number;
  title: string;
  content_type: ContentKind;
  published: boolean;
  total_teachers: number;
  completed: ContentProgressPerson[];
  not_completed: ContentProgressPerson[];
};

export type ContentProgressRecord = {
  teacher_id: number;
  teacher_name: string;
  teacher_email: string;
  content_id: number;
  content_title: string;
  content_type: ContentKind;
  status: CompletionStatus;
  progress_percent: number;
  completed_at: string | null;
};

export type ContentProgressRecordPage = {
  total: number;
  limit: number;
  offset: number;
  items: ContentProgressRecord[];
};

export type ContentProgressRecordFilters = {
  contentType?: ContentKind | "";
  status?: CompletionStatus | "";
  lessonId?: number | "";
  search?: string;
  limit?: number;
  offset?: number;
};

function queryString(params: Record<string, string | number | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") q.set(key, String(value));
  }
  const text = q.toString();
  return text ? `?${text}` : "";
}

export const contentProgressApi = {
  summary: (): Promise<ContentProgressSummary> => request("/admin/content-progress/summary"),
  teachers: (search?: string): Promise<ContentProgressTeacher[]> =>
    request(`/admin/content-progress/teachers${queryString({ search: search?.trim() })}`),
  contents: (contentType?: ContentKind | ""): Promise<ContentProgressItem[]> =>
    request(`/admin/content-progress/content${queryString({ content_type: contentType })}`),
  content: (lessonId: number): Promise<ContentProgressDetail> => request(`/admin/content-progress/content/${lessonId}`),
  records: (f: ContentProgressRecordFilters = {}): Promise<ContentProgressRecordPage> =>
    request(
      `/admin/content-progress/records${queryString({
        content_type: f.contentType,
        status: f.status,
        lesson_id: f.lessonId,
        search: f.search?.trim(),
        limit: f.limit,
        offset: f.offset,
      })}`,
    ),
};
