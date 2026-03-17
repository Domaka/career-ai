import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import "./App.css";

type Health = { status: string; message: string };

const API_BASE_URL = "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
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

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError("Select a PDF or DOCX CV before submitting.");
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

  return (
    <main className="app-shell">
      <section className="panel hero-panel">
        <p className="eyebrow">Career AI</p>
        <h1>Manual CV Extraction Test</h1>
        <p className="intro">
          Upload a real CV and inspect the backend response from the advanced CV
          intelligence engine.
        </p>
        <div className="health-pill">
          Backend status:{" "}
          <strong>{health?.status === "ok" ? health.message : "Unavailable"}</strong>
        </div>
      </section>

      <section className="panel form-panel">
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
            <span>Use OpenAI review when OPENAI_API_KEY is configured</span>
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
    </main>
  );
}