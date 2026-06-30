import { useEffect, useRef, useState, useCallback } from "react";
import { getWsUrl } from "@/lib/api";

export interface WsEvent {
  type: "event" | "complete" | "error";
  data: {
    agent?: string;
    status?: string;
    message?: string;
    timestamp?: string;
    run_id?: string;
    job_count?: number;
  };
}

export function useRunSocket(runId: string | null) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const maxRetries = 10;

  const connect = useCallback(() => {
    if (!runId) return;

    const ws = new WebSocket(getWsUrl(runId));
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setReconnecting(false);
      retriesRef.current = 0;
    };

    ws.onmessage = (msg) => {
      try {
        const parsed: WsEvent = JSON.parse(msg.data);
        setEvents((prev) => [...prev, parsed]);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (retriesRef.current < maxRetries) {
        setReconnecting(true);
        const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000);
        retriesRef.current += 1;
        setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [runId]);

  useEffect(() => {
    setEvents([]);
    retriesRef.current = 0;
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, reconnecting, clearEvents };
}
