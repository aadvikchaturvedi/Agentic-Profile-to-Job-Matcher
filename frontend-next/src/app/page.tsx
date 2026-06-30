"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Play,
  Pause,
  Square,
  Download,
  Clock,
  Globe,
  FileSearch,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  fetchRunDetail,
  fetchActiveResume,
  pauseRun,
  resumeRun,
  stopRun,
  getExportUrl,
} from "@/lib/api";
import { useRunSocket } from "@/hooks/useRunSocket";
import AgentLiveStream from "@/components/AgentLiveStream";
import ResultsGrid from "@/components/ResultsGrid";

function formatDuration(ms: number | null): string {
  if (!ms) return "—";
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

export default function Home() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [timer, setTimer] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { events, connected, reconnecting } = useRunSocket(activeRunId);

  const { data: resume } = useQuery({
    queryKey: ["activeResume"],
    queryFn: fetchActiveResume,
    refetchInterval: 10000,
  });

  const { data: runDetail, refetch: refetchRun } = useQuery({
    queryKey: ["run", activeRunId],
    queryFn: () => fetchRunDetail(activeRunId!, !!resume),
    enabled: !!activeRunId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" || query.state.data?.status === "pending"
        ? 2000
        : false,
  });

  // Listen for run selection from Sidebar
  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent).detail;
      setActiveRunId(id);
    };
    window.addEventListener("select-run", handler);
    return () => window.removeEventListener("select-run", handler);
  }, []);

  // Timer for running extractions
  useEffect(() => {
    if (runDetail?.status === "running" || runDetail?.status === "pending") {
      setTimer(0);
      timerRef.current = setInterval(() => {
        setTimer((t) => t + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [runDetail?.status]);

  const handlePause = useCallback(async () => {
    if (activeRunId) await pauseRun(activeRunId);
  }, [activeRunId]);

  const handleResume = useCallback(async () => {
    if (activeRunId) await resumeRun(activeRunId);
  }, [activeRunId]);

  const handleStop = useCallback(async () => {
    if (activeRunId) await stopRun(activeRunId);
  }, [activeRunId]);

  const isRunning = runDetail?.status === "running" || runDetail?.status === "pending";
  const isPaused = runDetail?.status === "paused";

  if (!activeRunId) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <FileSearch size={48} className="mx-auto text-[#d4d4d4] mb-4" />
          <h2 className="text-lg font-semibold text-[#6b6b6b]">
            Multi-Agent Job Extractor
          </h2>
          <p className="text-sm text-[#9e9e9e] mt-1">
            Select a run from the sidebar or start a new extraction.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="border-b border-[#e5e5e5] bg-white px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-sm font-semibold text-[#1c1c1e]">
              {runDetail?.domain || "Extraction"}
            </h1>
            <div className="flex items-center gap-3 mt-1">
              <span className="flex items-center gap-1 text-[11px] text-[#6b6b6b]">
                <Globe size={11} />
                {runDetail?.url || "—"}
              </span>
              <span className="flex items-center gap-1 text-[11px] text-[#6b6b6b]">
                <Clock size={11} />
                {isRunning
                  ? `${Math.floor(timer / 60)}m ${timer % 60}s`
                  : formatDuration(runDetail?.duration_ms ?? null)}
              </span>
              {reconnecting && (
                <span className="flex items-center gap-1 text-[11px] text-amber-600">
                  <WifiOff size={11} />
                  reconnecting...
                </span>
              )}
              {connected && !reconnecting && (
                <span className="flex items-center gap-1 text-[11px] text-green-600">
                  <Wifi size={11} />
                  live
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isRunning && !isPaused && (
              <button
                onClick={handlePause}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e5e5e5] text-[12px] font-medium text-[#6b6b6b] hover:bg-[#f5f5f5] transition-colors"
              >
                <Pause size={13} />
                Pause
              </button>
            )}
            {isPaused && (
              <button
                onClick={handleResume}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e5e5e5] text-[12px] font-medium text-[#6b6b6b] hover:bg-[#f5f5f5] transition-colors"
              >
                <Play size={13} />
                Resume
              </button>
            )}
            {isRunning && (
              <button
                onClick={handleStop}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 text-[12px] font-medium text-red-600 hover:bg-red-50 transition-colors"
              >
                <Square size={13} />
                Stop
              </button>
            )}
            <a
              href={getExportUrl(activeRunId, "json")}
              download
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e5e5e5] text-[12px] font-medium text-[#6b6b6b] hover:bg-[#f5f5f5] transition-colors"
            >
              <Download size={13} />
              JSON
            </a>
            <a
              href={getExportUrl(activeRunId, "csv")}
              download
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e5e5e5] text-[12px] font-medium text-[#6b6b6b] hover:bg-[#f5f5f5] transition-colors"
            >
              <Download size={13} />
              CSV
            </a>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Live stream */}
        <div>
          <h2 className="text-[11px] font-semibold text-[#6b6b6b] uppercase tracking-wider mb-3">
            Agent Pipeline
          </h2>
          <AgentLiveStream events={events} runStatus={runDetail?.status} />
        </div>

        {/* Results */}
        <div>
          <h2 className="text-[11px] font-semibold text-[#6b6b6b] uppercase tracking-wider mb-3">
            Results ({runDetail?.job_count || 0} jobs)
          </h2>
          <ResultsGrid jobs={runDetail?.jobs || []} resume={resume} />
        </div>
      </div>
    </div>
  );
}
