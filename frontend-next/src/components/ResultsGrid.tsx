"use client";

import { useState, useMemo } from "react";
import {
  Search,
  MapPin,
  Building,
  ChevronDown,
  ChevronRight,
  User,
  AlertCircle,
} from "lucide-react";
import { JobRecord, ResumeInfo } from "@/lib/api";

function ConfidenceBar({ score }: { score: number }) {
  const color =
    score >= 0.8
      ? "bg-green-500"
      : score >= 0.5
        ? "bg-amber-500"
        : "bg-gray-300";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>
      <span
        className={`text-[11px] font-medium ${
          score >= 0.8
            ? "text-green-600"
            : score >= 0.5
              ? "text-amber-600"
              : "text-gray-400"
        }`}
      >
        {Math.round(score * 100)}%
      </span>
    </div>
  );
}

function MatchScoreBadge({ score, llmScored }: { score: number | null; llmScored?: boolean }) {
  if (score === null || score === undefined) {
    return <span className="text-[11px] text-[#9e9e9e]">—</span>;
  }
  const color =
    score >= 7
      ? "bg-gray-900 text-white"
      : score >= 5
        ? "bg-gray-200 text-gray-700"
        : "bg-gray-100 text-gray-400";
  return (
    <span className="relative inline-flex items-center gap-1">
      <span className={`text-[12px] font-bold px-2 py-0.5 rounded ${color}`}>
        {score.toFixed(0)}
        <span className="text-[9px] opacity-60">/10</span>
      </span>
      {!llmScored && (
        <span className="text-[9px] text-[#9e9e9e]" title="Estimated from embedding similarity">
          ~
        </span>
      )}
    </span>
  );
}

function LocationBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    remote: "bg-green-100 text-green-700 border-green-200",
    hybrid: "bg-amber-100 text-amber-700 border-amber-200",
    onsite: "bg-blue-100 text-blue-700 border-blue-200",
  };
  return (
    <span
      className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${
        colors[type] || "bg-gray-100 text-gray-600 border-gray-200"
      }`}
    >
      {type}
    </span>
  );
}

function ExpandableRow({ job, hasResume }: { job: JobRecord; hasResume: boolean }) {
  const [open, setOpen] = useState(false);
  const match = job.match;

  return (
    <>
      <tr
        className="border-b border-[#f0f0f0] hover:bg-[#fafafa] transition-colors cursor-pointer"
        onClick={() => setOpen(!open)}
      >
        <td className="px-2 py-3 text-[#9e9e9e]">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </td>
        <td className="px-4 py-3 font-medium text-[#1c1c1e]">
          {job.title || "—"}
        </td>
        <td className="px-4 py-3 text-[#6b6b6b]">
          <div className="flex items-center gap-1.5">
            <Building size={12} />
            {job.company || "—"}
          </div>
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <MapPin size={12} className="text-[#9e9e9e]" />
            <LocationBadge type={job.location_type} />
            {job.location_raw && (
              <span className="text-[11px] text-[#9e9e9e] ml-1 truncate max-w-[80px]">
                {job.location_raw}
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-[13px] text-[#6b6b6b]">
          {job.salary_min && job.salary_max
            ? `${job.currency || "$"}${(job.salary_min / 1000).toFixed(0)}k–${(job.salary_max / 1000).toFixed(0)}k`
            : "—"}
        </td>
        <td className="px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {(job.tech_stack || []).slice(0, 3).map((tech) => (
              <span
                key={tech}
                className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200"
              >
                {tech}
              </span>
            ))}
            {(job.tech_stack || []).length > 3 && (
              <span className="text-[10px] text-[#9e9e9e]">
                +{job.tech_stack.length - 3}
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-right">
          <ConfidenceBar score={job.confidence} />
        </td>
        {hasResume && (
          <td className="px-4 py-3 text-center">
            <MatchScoreBadge
              score={match?.match_score ?? null}
              llmScored={match?.llm_scored}
            />
          </td>
        )}
      </tr>
      {open && hasResume && match && (
        <tr className="bg-[#fafafa]">
          <td colSpan={hasResume ? 8 : 7} className="px-4 py-3">
            <div className="flex gap-6 text-[13px]">
              <div className="flex-1">
                <p className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider mb-2">
                  Skill Match
                </p>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {match.matched_skills.map((s) => (
                    <span
                      key={s}
                      className="text-[11px] px-2 py-0.5 rounded bg-green-100 text-green-700 border border-green-200"
                    >
                      {s}
                    </span>
                  ))}
                  {match.missing_skills.map((s) => (
                    <span
                      key={s}
                      className="text-[11px] px-2 py-0.5 rounded bg-gray-100 text-gray-400 border border-gray-200"
                    >
                      {s}
                    </span>
                  ))}
                </div>
                {match.improvement_notes && (
                  <>
                    <p className="text-[11px] font-medium text-[#6b6b6b] uppercase tracking-wider mb-1">
                      Notes
                    </p>
                    <p className="text-[12px] text-[#6b6b6b] leading-relaxed">
                      {match.improvement_notes}
                    </p>
                  </>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ResultsGrid({
  jobs,
  resume,
}: {
  jobs: JobRecord[];
  resume?: ResumeInfo | null;
}) {
  const [search, setSearch] = useState("");
  const [locationFilter, setLocationFilter] = useState<string | null>(null);
  const [strongOnly, setStrongOnly] = useState(false);
  const [sortBy, setSortBy] = useState<"default" | "match">("default");

  const hasResume = !!resume;

  const filtered = useMemo(() => {
    let items = [...jobs];
    if (search) {
      const q = search.toLowerCase();
      items = items.filter(
        (j) =>
          j.title.toLowerCase().includes(q) ||
          j.company.toLowerCase().includes(q) ||
          j.tech_stack.some((t) => t.toLowerCase().includes(q))
      );
    }
    if (locationFilter) {
      items = items.filter((j) => j.location_type === locationFilter);
    }
    if (strongOnly && hasResume) {
      items = items.filter(
        (j) => j.match && j.match.match_score !== null && j.match.match_score >= 7
      );
    }
    if (sortBy === "match" && hasResume) {
      items.sort((a, b) => {
        const sa = a.match?.match_score ?? 0;
        const sb = b.match?.match_score ?? 0;
        return sb - sa;
      });
    }
    return items;
  }, [jobs, search, locationFilter, strongOnly, sortBy, hasResume]);

  if (jobs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-[#9e9e9e] text-sm">
        No jobs found for this URL.
      </div>
    );
  }

  return (
    <div>
      {/* Search & filters */}
      <div className="flex items-center gap-3 mb-4">
        <div className="flex-1 relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9e9e9e]"
          />
          <input
            type="text"
            placeholder="Search by title, company, or tech..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-[#e5e5e5] text-[13px] bg-white focus:outline-none focus:border-[#6366f1] transition-colors"
          />
        </div>
        <div className="flex gap-1">
          {["remote", "hybrid", "onsite"].map((lt) => (
            <button
              key={lt}
              onClick={() =>
                setLocationFilter(locationFilter === lt ? null : lt)
              }
              className={`px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-colors ${
                locationFilter === lt
                  ? "bg-[#6366f1] text-white border-[#6366f1]"
                  : "bg-white text-[#6b6b6b] border-[#e5e5e5] hover:border-[#6366f1]"
              }`}
            >
              {lt}
            </button>
          ))}
        </div>
        {hasResume && (
          <>
            <button
              onClick={() => setStrongOnly(!strongOnly)}
              className={`px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-colors ${
                strongOnly
                  ? "bg-[#6366f1] text-white border-[#6366f1]"
                  : "bg-white text-[#6b6b6b] border-[#e5e5e5] hover:border-[#6366f1]"
              }`}
            >
              Strong matches (≥7)
            </button>
            <button
              onClick={() =>
                setSortBy(sortBy === "match" ? "default" : "match")
              }
              className={`px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-colors ${
                sortBy === "match"
                  ? "bg-[#6366f1] text-white border-[#6366f1]"
                  : "bg-white text-[#6b6b6b] border-[#e5e5e5] hover:border-[#6366f1]"
              }`}
            >
              Sort by match
            </button>
          </>
        )}
      </div>

      {/* No resume banner */}
      {!hasResume && jobs.length > 0 && (
        <div className="mb-3 flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-50 border border-[#e5e5e5]">
          <AlertCircle size={14} className="text-[#9e9e9e]" />
          <span className="text-[12px] text-[#6b6b6b]">
            Upload a resume in the sidebar to see match scores.
          </span>
        </div>
      )}

      {/* Table */}
      <div className="border border-[#e5e5e5] rounded-lg overflow-hidden bg-white">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-[#e5e5e5] bg-[#fafafa]">
              <th className="w-8 px-2 py-2.5" />
              <th className="text-left px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                Title
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                Company
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                Location
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                Salary
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                Tech Stack
              </th>
              <th className="text-right px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                Confidence
              </th>
              {hasResume && (
                <th className="text-center px-4 py-2.5 font-medium text-[#6b6b6b] text-[11px] uppercase tracking-wider">
                  Match
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {filtered.map((job) => (
              <ExpandableRow key={job.id} job={job} hasResume={hasResume} />
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="p-8 text-center text-[#9e9e9e] text-sm">
            No jobs match your filters.
          </div>
        )}
      </div>
      <p className="text-[11px] text-[#9e9e9e] mt-2">
        Showing {filtered.length} of {jobs.length} jobs
        {strongOnly && " (strong matches only)"}
      </p>
    </div>
  );
}
