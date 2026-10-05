import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";

const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

type Mode = "etl" | "gtm";

type EtlOutput = { constraints: unknown };
type GtmOutput = { message: string; pptxPath: string };
type OutputState = { mode: "etl"; data: EtlOutput } | { mode: "gtm"; data: GtmOutput } | null;

export default function App() {
  const [mode, setMode] = useState<Mode>("gtm");
  const [userPrompt, setUserPrompt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<OutputState>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    setFiles((prev) => [...prev, ...accepted]);
    setBackendError(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
        ".xlsm",
      ],
      "application/vnd.ms-excel": [".xls"],
      "application/json": [".json"],
      "application/xml": [".xml"],
      "text/xml": [".xml"],
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": [
        ".pptx",
      ],
    },
    multiple: true,
  });

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const executePipeline = async () => {
    setLoading(true);
    setBackendError(null);
    setOutput(null);

    const formData = new FormData();
    formData.append("mode", mode);
    if (userPrompt.trim() !== "") {
      formData.append("user_prompt", userPrompt);
    }
    files.forEach((file) => {
      formData.append("reference_files", file);
    });

    try {
      const { data } = await axios.post<{
        success: boolean;
        mode: string;
        constraints?: unknown;
        message?: string;
        pptx_path?: string;
      }>(`${API_BASE}/api/generate`, formData, {
        timeout: 1_800_000,
      });

      if (data.mode === "etl" && data.constraints !== undefined) {
        setOutput({ mode: "etl", data: { constraints: data.constraints } });
      } else if (data.mode === "gtm" && data.pptx_path) {
        setOutput({
          mode: "gtm",
          data: {
            message: data.message ?? "Presentation generated successfully.",
            pptxPath: data.pptx_path,
          },
        });
      } else {
        setBackendError("Unexpected response shape from server.");
      }
    } catch (error) {
      console.error("Full Error Object:", error);
      let errorMsg = "An unknown error occurred.";

      if (axios.isAxiosError(error)) {
        if (error.response) {
          const data = error.response.data as unknown;
          let detail: string;
          if (
            data &&
            typeof data === "object" &&
            "detail" in data &&
            (data as { detail: unknown }).detail != null
          ) {
            const d = (data as { detail: unknown }).detail;
            detail = typeof d === "string" ? d : JSON.stringify(d);
          } else {
            detail =
              typeof data === "string" ? data : JSON.stringify(data ?? {});
          }
          errorMsg = `Backend API Error [${error.response.status}]: ${detail}`;
        } else if (error.request) {
          errorMsg =
            "Network Error: The FastAPI backend is unreachable. Is Docker running on port 8000?";
        } else {
          errorMsg = `Request Setup Error: ${error.message}`;
        }
      } else {
        errorMsg = error instanceof Error ? error.message : String(error);
      }

      setBackendError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const downloadHref = `${API_BASE}/api/download/presentation`;

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 via-slate-950 to-zinc-950">
      <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        <header className="mb-10 border-b border-zinc-800/80 pb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
            ReluLayer
          </p>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-zinc-50 sm:text-4xl">
            ReluLayer Deterministic Engine
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-400">
            Agentic ETL and GTM pipelines against a single switchboard. Upload reference
            artifacts, choose a mode, and execute.
          </p>
        </header>

        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm font-medium text-zinc-400">Pipeline mode</span>
          <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900/50 p-1 shadow-inner shadow-black/40">
            <button
              type="button"
              onClick={() => {
                setMode("gtm");
                setOutput(null);
              }}
              className={`rounded-md px-5 py-2 text-sm font-medium transition ${
                mode === "gtm"
                  ? "bg-slate-700 text-white shadow-sm ring-1 ring-white/10"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              GTM
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("etl");
                setOutput(null);
              }}
              className={`rounded-md px-5 py-2 text-sm font-medium transition ${
                mode === "etl"
                  ? "bg-slate-700 text-white shadow-sm ring-1 ring-white/10"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              ETL
            </button>
          </div>
        </div>

        <div className="mb-6">
          <label
            htmlFor="pipeline-instructions"
            className="mb-2 block text-sm font-medium text-zinc-300"
          >
            Pipeline Instructions (Optional)
          </label>
          <p className="mb-2 text-xs text-zinc-500">
            Directives for the model only. Uploaded files are treated as data, not instructions.
          </p>
          <textarea
            id="pipeline-instructions"
            name="user_prompt"
            className="h-32 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-900 p-4 font-mono text-sm leading-relaxed text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Enter explicit instructions for the pipeline (e.g., 'Draft a 5-slide pitch deck focusing on deterministic execution...')"
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            disabled={loading}
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        <div
          {...getRootProps()}
          className={`relative flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 transition ${
            isDragActive
              ? "border-sky-500/40 bg-slate-900/50"
              : "border-zinc-700 bg-zinc-900/30 hover:border-zinc-600 hover:bg-zinc-900/50"
          }`}
        >
          <input {...getInputProps()} />
          <div className="text-center">
            <p className="text-sm font-medium text-zinc-200">
              {isDragActive ? "Drop files here" : "Drag & drop reference files"}
            </p>
            <p className="mt-2 text-xs text-zinc-500">
              CSV, XLSX, JSON, XML, PPTX (template) — or click to browse
            </p>
          </div>
        </div>

        {files.length > 0 && (
          <ul className="mt-4 space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
            {files.map((f, i) => (
              <li
                key={`${f.name}-${i}`}
                className="flex items-center justify-between gap-3 text-sm text-zinc-300"
              >
                <span className="truncate font-mono text-xs">{f.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(i)}
                  className="shrink-0 text-xs text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-8">
          <button
            type="button"
            onClick={executePipeline}
            disabled={loading}
            className="w-full rounded-lg bg-slate-600 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/50 transition hover:bg-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Executing…" : "Execute Pipeline"}
          </button>
        </div>

        {backendError && (
          <div
            className="mt-6 rounded-lg border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-200"
            role="alert"
          >
            {backendError}
          </div>
        )}

        {output?.mode === "etl" && (
          <section className="mt-10">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
              Constraints (schema)
            </h2>
            <pre className="overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-xs leading-relaxed text-emerald-100/90">
              <code>{JSON.stringify(output.data.constraints, null, 2)}</code>
            </pre>
          </section>
        )}

        {output?.mode === "gtm" && (
          <section className="mt-10">
            <div className="rounded-xl border border-emerald-900/40 bg-emerald-950/30 px-5 py-4">
              <p className="text-sm font-medium text-emerald-100">
                {output.data.message}
              </p>
              <p className="mt-2 font-mono text-xs text-emerald-200/70">
                {output.data.pptxPath}
              </p>
              <a
                href={downloadHref}
                download
                className="mt-4 inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow hover:bg-emerald-500"
              >
                Download Presentation
              </a>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
