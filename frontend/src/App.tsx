import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import "./App.css";

type Health = { status: string; message: string };
type AuthUser = { id: number; username: string; email: string };
type Page = "/login" | "/dashboard";

const API_BASE_URL = "http://localhost:8000";

export default function App() {
  const [page, setPage] = useState<Page>(() =>
    window.location.pathname === "/dashboard" ? "/dashboard" : "/login"
  );
  const [health, setHealth] = useState<Health | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authUsername, setAuthUsername] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authToken, setAuthToken] = useState<string | null>(() =>
    localStorage.getItem("career_ai_token")
  );
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem("career_ai_user");
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  });
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [profileId, setProfileId] = useState("101");
  const [targetRole, setTargetRole] = useState("Backend Django Developer");
  const [useLlm, setUseLlm] = useState(true);
  const [autoLearn, setAutoLearn] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/health/`)
      .then((res) => res.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    const onPopState = () => {
      setPage(window.location.pathname === "/dashboard" ? "/dashboard" : "/login");
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (authToken && page === "/login") {
      navigateTo("/dashboard");
    }

    if (!authToken && page === "/dashboard") {
      navigateTo("/login");
    }
  }, [authToken, page]);

  const navigateTo = (nextPage: Page) => {
    if (window.location.pathname !== nextPage) {
      window.history.pushState({}, "", nextPage);
    }
    setPage(nextPage);
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
  };

  const handleAuthSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthError(null);
    setAuthLoading(true);

    const endpoint = authMode === "register" ? "/api/auth/register/" : "/api/auth/login/";
    const body =
      authMode === "register"
        ? { username: authUsername, password: authPassword, email: authEmail }
        : { username: authUsername, password: authPassword };

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = (await response.json()) as {
        token?: string;
        user?: AuthUser;
        error?: string;
      };

      if (!response.ok || !payload.token || !payload.user) {
        throw new Error(payload.error || "Authentication failed.");
      }

      setAuthToken(payload.token);
      setAuthUser(payload.user);
      localStorage.setItem("career_ai_token", payload.token);
      localStorage.setItem("career_ai_user", JSON.stringify(payload.user));
      setAuthPassword("");
      navigateTo("/dashboard");
    } catch (submitError) {
      setAuthError(submitError instanceof Error ? submitError.message : "Authentication failed.");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    if (!authToken) {
      return;
    }

    try {
      await fetch(`${API_BASE_URL}/api/auth/logout/`, {
        method: "POST",
        headers: { Authorization: `Token ${authToken}` },
      });
    } catch {
      // no-op: we clear local session either way
    }

    setAuthToken(null);
    setAuthUser(null);
    localStorage.removeItem("career_ai_token");
    localStorage.removeItem("career_ai_user");
    navigateTo("/login");
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError("Select a PDF or DOCX CV before submitting.");
      return;
    }

    if (!authToken) {
      setError("Please sign in before uploading a CV.");
      return;
    }

    const formData = new FormData();
    formData.append("profile_id", profileId);
    formData.append("target_role", targetRole);
    formData.append("use_llm", String(useLlm));
    formData.append("auto_learn", String(autoLearn));
    formData.append("cv_file", file);

    setIsUploading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/cv/extract/`, {
        method: "POST",
        headers: { Authorization: `Token ${authToken}` },
        body: formData,
      });

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        const message =
          typeof payload === "object" &&
          payload !== null &&
          "error" in payload &&
          typeof (payload as { error?: unknown }).error === "string"
            ? (payload as { error: string }).error
            : "Upload failed.";

        throw new Error(message);
      }

      setResult(payload);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  };

  const isDashboard = page === "/dashboard";

  return (
    <main className="app-shell">
      <header className="panel hero-panel">
        <p className="eyebrow">Career AI</p>
        <h1>{isDashboard ? "Dashboard" : "Login"}</h1>
        <p className="intro">
          {isDashboard
            ? "Upload a CV from your dashboard and review extraction plus analysis output."
            : "Sign in or create an account to access the extraction dashboard."}
        </p>
        <div className="health-pill">
          Backend status:{" "}
          <strong>{health?.status === "ok" ? health.message : "Unavailable"}</strong>
        </div>
        {isDashboard ? (
          <div className="header-actions">
            <button type="button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        ) : null}
      </header>

      {!isDashboard ? (
        <section className="panel auth-panel">
          <h2>Authentication</h2>
          <div className="auth-toggle">
            <button
              type="button"
              className={authMode === "login" ? "active" : ""}
              onClick={() => setAuthMode("login")}
            >
              Login
            </button>
            <button
              type="button"
              className={authMode === "register" ? "active" : ""}
              onClick={() => setAuthMode("register")}
            >
              Register
            </button>
          </div>

          <form className="upload-form" onSubmit={handleAuthSubmit}>
            <label>
              Username
              <input
                type="text"
                value={authUsername}
                onChange={(event) => setAuthUsername(event.target.value)}
              />
            </label>

            {authMode === "register" ? (
              <label>
                Email
                <input
                  type="email"
                  value={authEmail}
                  onChange={(event) => setAuthEmail(event.target.value)}
                />
              </label>
            ) : null}

            <label>
              Password
              <input
                type="password"
                value={authPassword}
                onChange={(event) => setAuthPassword(event.target.value)}
              />
            </label>

            <button type="submit" disabled={authLoading}>
              {authLoading
                ? "Submitting..."
                : authMode === "register"
                  ? "Create Account"
                  : "Login"}
            </button>
          </form>
          {authError ? <p className="error-banner">{authError}</p> : null}
        </section>
      ) : (
        <>
          <section className="panel form-panel">
            <div className="auth-status">
              <p>
                Signed in as <strong>{authUser?.username ?? "User"}</strong>
              </p>
            </div>

            <form className="upload-form" onSubmit={handleSubmit}>
              <label>
                Profile ID
                <input
                  type="number"
                  min="1"
                  value={profileId}
                  onChange={(event) => setProfileId(event.target.value)}
                />
              </label>

              <label>
                Target Role
                <input
                  type="text"
                  value={targetRole}
                  onChange={(event) => setTargetRole(event.target.value)}
                />
              </label>

              <label>
                CV File
                <input type="file" accept=".pdf,.docx" onChange={handleFileChange} />
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={useLlm}
                  onChange={(event) => setUseLlm(event.target.checked)}
                />
                <span>Use Gemini review when GEMINI_API_KEY is configured</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={autoLearn}
                  onChange={(event) => setAutoLearn(event.target.checked)}
                  disabled={!useLlm}
                />
                <span>Auto-apply only safe learning-rule updates</span>
              </label>

              <button type="submit" disabled={isUploading}>
                {isUploading ? "Extracting..." : "Upload CV"}
              </button>
            </form>

            {file ? <p className="file-note">Selected file: {file.name}</p> : null}
            {error ? <p className="error-banner">{error}</p> : null}
          </section>

          <section className="panel response-panel">
            <div className="response-header">
              <h2>API Response</h2>
              <span>POST {API_BASE_URL}/api/cv/extract/</span>
            </div>
            <pre>{JSON.stringify(result, null, 2) || "Submit a CV to see the response."}</pre>
          </section>
        </>
      )}
    </main>
  );
}