"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileSearch,
  Plus,
  Clock,
  Cpu,
  HardDrive,
  Upload,
  FileText,
  Trash2,
  User,
} from "lucide-react";
import {
  fetchHealth,
  fetchRuns,
  fetchActiveResume,
  uploadResume,
  deleteResume,
  RunSummary,
  ResumeInfo,
  createRun,
} from "@/lib/api";

function StatusDot({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "#22c55e"
      : status === "running" || status === "pending"
        ? "#f59e0b"
        : status === "failed"
          ? "#ef4444"
          : "#9e9e9e";
  return (
    <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
  );
}

function RelativeTime({ dateStr }: { dateStr: string }) {
  const [label, setLabel] = useState("");
  useEffect(() => {
    const update = () => {
      const diff = Date.now() - new Date(dateStr).getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) setLabel("just now");
      else if (mins < 60) setLabel(`${mins}m ago`);
      else if (mins < 1440) setLabel(`${Math.floor(mins / 60)}h ago`);
      else setLabel(`${Math.floor(mins / 1440)}d ago`);
    };
    update();
    const id = setInterval(update, 30000);
    return () => clearInterval(id);
  }, [dateStr]);
  return <>{label}</>;
}

function GroupedRuns({ runs, onSelect, activeId }: {
  runs: RunSummary[];
  onSelect: (id: string) => void;
  activeId: string | null;
}) {
  const groups: Record<string, RunSummary[]> = {};
  for (const r of runs) {
    const date = new Date(r.created_at).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(r);
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-3 px-2">
      {Object.entries(groups).map(([date, items]) => (
        <div key={date}>
          <p className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider mb-1 px-2">
            {date}
          </p>
          {items.map((r) => (
            <button
              key={r.id}
              onClick={() => onSelect(r.id)}
              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                activeId === r.id
                  ? "bg-[#2c2c2e] text-white"
                  : "text-[#9e9e9e] hover:bg-[#2c2c2e] hover:text-white"
              }`}
            >
              <div className="flex items-center gap-2">
                <StatusDot status={r.status} />
                <span className="truncate flex-1 text-[13px]">{r.domain}</span>
              </div>
              <div className="flex items-center gap-2 mt-1 text-[11px] text-[#6b6b6b]">
                <span className="flex items-center gap-1">
                  <FileSearch size={10} />
                  {r.job_count} jobs
                </span>
                <span>·</span>
                <span className="flex items-center gap-1">
                  <Clock size={10} />
                  {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
                </span>
                <span>·</span>
                <RelativeTime dateStr={r.created_at} />
              </div>
              {r.latest_event && (
                <p className="text-[11px] text-[#6b6b6b] mt-1 truncate">
                  {r.latest_event}
                </p>
              )}
            </button>
          ))}
        </div>
      ))}
      {runs.length === 0 && (
        <p className="text-[12px] text-[#6b6b6b] px-2">No runs yet</p>
      )}
    </div>
  );
}

export default function Sidebar() {
  const queryClient = useQueryClient();
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(3);
  const [creating, setCreating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 10000,
  });
  const { data: runs, refetch: refetchRuns } = useQuery({
    queryKey: ["runs"],
    queryFn: fetchRuns,
    refetchInterval: 5000,
  });
  const { data: resume, refetch: refetchResume } = useQuery({
    queryKey: ["activeResume"],
    queryFn: fetchActiveResume,
    refetchInterval: 10000,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      refetchResume();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteResume,
    onSuccess: () => {
      refetchResume();
    },
  });

  const handleSelectRun = useCallback((id: string) => {
    setActiveRunId(id);
    window.dispatchEvent(new CustomEvent("select-run", { detail: id }));
  }, []);

  const handleCreateRun = async () => {
    if (!url) return;
    setCreating(true);
    try {
      const result = await createRun(url, maxPages);
      setUrl("");
      setShowForm(false);
      await refetchRuns();
      handleSelectRun(result.run_id);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await uploadMutation.mutateAsync(file);
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <aside className="w-72 bg-[#1c1c1e] text-white flex flex-col shrink-0 border-r border-[#2c2c2e]">
      {/* Brand */}
      <div className="px-4 py-4 border-b border-[#2c2c2e]">
        <div className="flex items-center gap-2">
          <FileSearch size={18} className="text-[#6366f1]" />
          <span className="font-semibold text-sm">Job Extract</span>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              health?.status === "ok"
                ? "bg-green-500"
                : "bg-red-500 animate-pulse-dot"
            }`}
          />
          <span className="text-[11px] text-[#6b6b6b]">
            {health?.status === "ok"
              ? "Local Backend: Connected"
              : "Local Backend: Disconnected"}
          </span>
        </div>
      </div>

      {/* Resume */}
      <div className="px-3 py-3 border-b border-[#2c2c2e]">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider flex items-center gap-1">
            <User size={11} />
            Resume
          </span>
          {resume && (
            <button
              onClick={() => deleteMutation.mutate(resume.id)}
              className="text-[#6b6b6b] hover:text-red-400 transition-colors"
              title="Remove resume"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
        {resume ? (
          <div className="bg-[#2c2c2e] rounded-md px-3 py-2 text-[12px]">
            <div className="flex items-center gap-2 text-[#9e9e9e]">
              <FileText size={12} />
              <span className="truncate flex-1">{resume.filename}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {resume.parsed_skills.slice(0, 4).map((s) => (
                <span key={s} className="text-[10px] px-1 py-0.5 rounded bg-[#3a3a3c] text-[#9e9e9e]">
                  {s}
                </span>
              ))}
              {resume.parsed_skills.length > 4 && (
                <span className="text-[10px] text-[#6b6b6b]">+{resume.parsed_skills.length - 4}</span>
              )}
            </div>
            {resume.years_experience && (
              <p className="text-[10px] text-[#6b6b6b] mt-1">
                {resume.years_experience} yr exp · {resume.seniority_level}
              </p>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mt-1.5 text-[10px] text-[#6366f1] hover:text-[#4f46e5] transition-colors"
            >
              Swap resume
            </button>
          </div>
        ) : (
          <div
            onClick={() => fileInputRef.current?.click()}
            className="border border-dashed border-[#3a3a3c] rounded-md px-3 py-4 text-center cursor-pointer hover:border-[#6366f1] transition-colors"
          >
            <Upload size={16} className="mx-auto text-[#6b6b6b] mb-1" />
            <p className="text-[11px] text-[#6b6b6b]">
              Upload resume (PDF or text)
            </p>
            <p className="text-[10px] text-[#6b6b6b] mt-0.5">
              Enables AI job matching
            </p>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {/* New Extraction */}
      <div className="px-3 py-3 border-b border-[#2c2c2e]">
        <button
          onClick={() => setShowForm(!showForm)}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-[#6366f1] hover:bg-[#4f46e5] text-white text-sm font-medium transition-colors disabled:opacity-50"
        >
          <Plus size={16} />
          New Extraction
        </button>
        {showForm && (
          <div className="mt-3 space-y-2">
            <input
              type="url"
              placeholder="https://example.com/jobs"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full px-3 py-2 rounded-md bg-[#2c2c2e] border border-[#3a3a3c] text-white text-[13px] placeholder:text-[#6b6b6b] focus:outline-none focus:border-[#6366f1]"
            />
            <div className="flex items-center gap-2">
              <label className="text-[11px] text-[#6b6b6b]">Max pages:</label>
              <input
                type="number"
                min={1}
                max={10}
                value={maxPages}
                onChange={(e) => setMaxPages(Math.max(1, Math.min(10, Number(e.target.value))))}
                className="w-16 px-2 py-1 rounded-md bg-[#2c2c2e] border border-[#3a3a3c] text-white text-[13px] text-center focus:outline-none focus:border-[#6366f1]"
              />
            </div>
            <button
              onClick={handleCreateRun}
              disabled={!url || creating}
              className="w-full py-1.5 rounded-md bg-[#6366f1] hover:bg-[#4f46e5] text-white text-[13px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {creating ? "Starting..." : "Start Extraction"}
            </button>
          </div>
        )}
      </div>

      {/* Run history label */}
      <div className="px-4 py-2">
        <p className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider">
          Run History
        </p>
      </div>

      {/* Runs list */}
      <GroupedRuns
        runs={runs || []}
        onSelect={handleSelectRun}
        activeId={activeRunId}
      />

      {/* Resource metrics */}
      <div className="px-4 py-3 border-t border-[#2c2c2e] space-y-1.5">
        <p className="text-[10px] text-[#6b6b6b] uppercase tracking-wider font-medium">
          System
        </p>
        <div className="flex items-center gap-2 text-[11px] text-[#6b6b6b]">
          <Cpu size={12} />
          <span>CPU {health?.cpu_percent?.toFixed(0) ?? "—"}%</span>
          <HardDrive size={12} />
          <span>MEM {health?.memory_percent?.toFixed(0) ?? "—"}%</span>
        </div>
      </div>
    </aside>
  );
}
