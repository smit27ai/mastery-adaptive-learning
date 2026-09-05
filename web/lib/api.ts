/**
 * Typed client for the Mastery API.
 *
 * These types mirror the Pydantic response models in src/mastery/common/schemas.py.
 * When a schema changes there, it changes here - that pairing is deliberate, since a
 * silently mismatched field is the easiest way to break the live demo.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface MasteryEntry {
  concept_id: number;
  concept_name: string;
  mastery: number;
  attempts: number;
}

export interface Question {
  id: number;
  concept_id: number;
  concept_name: string;
  text: string;
  options: string[];
  difficulty: number;
}

export interface NextQuestion {
  question: Question;
  mastery: MasteryEntry[];
  why: string;
  policy: string;
  predicted_p_correct: number;
  model_version: string;
}

export interface SubmitResult {
  correct: boolean;
  correct_answer: string;
  mastery_before: number;
  mastery_after: number;
  concept_id: number;
  concept_name: string;
  explanation: string;
  anomaly_flag: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  role: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
      cache: "no-store",
    });
  } catch {
    // A network-level failure means the API is not running; say so plainly rather
    // than surfacing a bare TypeError to the learner.
    throw new ApiError(
      "Cannot reach the Mastery API. Is the backend running on " + API_URL + "?",
      0,
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, role: "student" }),
    }),

  nextQuestion: (token: string, sessionId?: string) =>
    request<NextQuestion>(
      `/next-question${sessionId ? `?session_id=${sessionId}` : ""}`,
      {},
      token,
    ),

  submitAnswer: (
    token: string,
    payload: {
      question_id: number;
      answer: string;
      response_time_ms: number;
      hints_used?: number;
      session_id?: string;
    },
  ) =>
    request<SubmitResult>(
      "/submit-answer",
      { method: "POST", body: JSON.stringify(payload) },
      token,
    ),

  startSession: (token: string) =>
    request<{ session_id: string; started_at: string }>(
      "/session/start",
      { method: "POST" },
      token,
    ),
};

const TOKEN_KEY = "mastery.token";

export const session = {
  get(): string | null {
    if (typeof window === "undefined") return null;
    try {
      return window.localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string): void {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* private mode or blocked storage - the app still works for this session */
    }
  },
  clear(): void {
    try {
      window.localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* nothing to do */
    }
  },
};
