"use client";

import { useRef, useEffect } from "react";
import { WsEvent } from "@/hooks/useRunSocket";
import { Loader } from "lucide-react";

const AGENT_COLORS: Record<string, string> = {
  scraper: "text-amber-400",
  parser: "text-blue-400",
  enrichment: "text-emerald-400",
  matching: "text-violet-400",
  pipeline: "text-purple-400",
};

const AGENT_LABELS: Record<string, string> = {
  scraper: "Scraper",
  parser: "Parser",
  enrichment: "Enrichment",
  matching: "Matching",
  pipeline: "Pipeline",
};

const AGENT_ORDER = ["scraper", "parser", "enrichment", "matching"];

function AgentStatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle: "bg-[#2c2c2e] text-[#6b6b6b]",
    started: "bg-[#2c2c2e] text-yellow-400",
    running: "bg-[#2c2c2e] text-yellow-400",
    progress: "bg-[#2c2c2e] text-yellow-400",
    completed: "bg-[#2c2c2e] text-green-400",
    failed: "bg-[#2c2c2e] text-red-400",
    skipped: "bg-[#2c2c2e] text-[#6b6b6b]",
  };
  return (
    <span
      className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
        colors[status] || "bg-[#2c2c2e] text-[#6b6b6b]"
      }`}
    >
      {status === "started" || status === "progress" ? "running" : status}
    </span>
  );
}

function AgentTrack({
  name,
  events,
  runStatus,
}: {
  name: string;
  events: WsEvent[];
  runStatus?: string;
}) {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [events]);

  const agentEvents = events.filter((e) => e.data.agent === name);
  const status =
    agentEvents.length === 0
      ? "idle"
      : [...agentEvents]
          .reverse()
          .find((e) =>
            ["completed", "failed", "started", "progress", "skipped"].includes(
              e.data.status || ""
            )
          )?.data.status || "idle";

  const isRunFailed = runStatus === "failed";

  return (
    <div className="border border-[#e5e5e5] rounded-lg bg-white overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#e5e5e5] bg-[#fafafa]">
        <div className="flex items-center gap-2">
          <span
            className={`text-sm font-medium ${
              AGENT_COLORS[name] || "text-gray-600"
            }`}
          >
            {AGENT_LABELS[name] || name}
          </span>
          {(status === "started" || status === "progress" || status === "running") && (
            <Loader size={12} className="animate-spin text-yellow-500" />
          )}
        </div>
        <AgentStatusPill status={status || "idle"} />
      </div>
      <div className="h-40 overflow-y-auto p-2 font-mono text-[11px] leading-relaxed bg-[#fafafa]">
        {agentEvents.length === 0 && (
          <p
            className={`italic ${
              isRunFailed ? "text-red-500 font-medium" : "text-[#9e9e9e]"
            }`}
          >
            {isRunFailed
              ? "Run failed before this agent could start."
              : "Waiting..."}
          </p>
        )}
        {agentEvents.map((e, i) => (
          <div
            key={i}
            className={`${
              e.data.status === "failed"
                ? "text-red-600 font-semibold bg-red-50 border border-red-200 rounded px-1.5 py-1 my-0.5"
                : e.data.status === "completed"
                  ? "text-green-600"
                  : e.data.status === "skipped"
                    ? "text-gray-400 italic"
                    : e.data.status === "started" || e.data.status === "progress"
                      ? "text-gray-700"
                      : "text-gray-500"
            }`}
          >
            <span className="text-[#9e9e9e] mr-1 font-normal">
              {e.data.timestamp
                ? new Date(e.data.timestamp).toLocaleTimeString()
                : ""}
            </span>
            {">"} {e.data.message}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

export default function AgentLiveStream({
  events,
  runStatus,
}: {
  events: WsEvent[];
  runStatus?: string;
}) {
  const failedEvent = events.find((e) => e.data.status === "failed");
  const isRunFailed = runStatus === "failed";

  return (
    <div className="space-y-3">
      {isRunFailed && (
        <div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200">
          <p className="text-[12px] font-semibold text-red-700 mb-1">
            Run failed
          </p>
          <p className="text-[12px] text-red-600">
            {failedEvent?.data.message ||
              "The pipeline failed. See the agent logs below for details."}
          </p>
        </div>
      )}
      {AGENT_ORDER.map((name) => (
        <AgentTrack
          key={name}
          name={name}
          events={events}
          runStatus={runStatus}
        />
      ))}
    </div>
  );
}
