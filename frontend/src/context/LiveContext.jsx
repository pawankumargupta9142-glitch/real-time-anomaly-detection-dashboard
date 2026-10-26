import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { LiveSocket } from "../api/websocket";
import { api } from "../api/client";

const LiveContext = createContext(null);

export function LiveProvider({ children }) {
  const [connection, setConnection] = useState("Disconnected");
  const [liveEvents, setLiveEvents] = useState([]);
  const [liveAlerts, setLiveAlerts] = useState([]);
  const [simStatus, setSimStatus] = useState(null);
  const [simulatorBusy, setSimulatorBusy] = useState(false);
  const [statsTick, setStatsTick] = useState(0);
  const [liveError, setLiveError] = useState(null);
  const toastGuard = useRef(new Set());
  const simulatorToggleInFlight = useRef(false);
  const simulatorStatusRevision = useRef(0);

  useEffect(() => {
    let active = true;
    const initialStatusRevision = simulatorStatusRevision.current;
    api.simulatorStatus()
      .then((res) => {
        if (active && simulatorStatusRevision.current === initialStatusRevision) {
          setSimStatus(res.data);
        }
      })
      .catch((error) => {
        if (active) {
          setLiveError(
            error.response?.data?.detail || "Unable to load simulator status. Check the backend connection."
          );
        }
      });
    api.recentEvents(30)
      .then((res) => {
        if (!active) return;
        setLiveEvents((current) => {
          const seen = new Set(current.map((event) => event.id ?? event.event_id));
          return [
            ...current,
            ...res.data.filter((event) => !seen.has(event.id ?? event.event_id)),
          ].slice(0, 100);
        });
      })
      .catch((error) => {
        if (active) {
          setLiveError(
            error.response?.data?.detail || "Unable to load recent events. Check the backend connection."
          );
        }
      });

    const socket = new LiveSocket({
      onConnection: setConnection,
      onEvent: (event) => {
        setLiveError(null);
        setLiveEvents((prev) => [event, ...prev.filter(
          (item) => (item.id ?? item.event_id) !== (event.id ?? event.event_id)
        )].slice(0, 100));
        setStatsTick((t) => t + 1);
        if (event.risk_level === "Critical" || (event.is_anomaly && event.risk_score >= 90)) {
          // Visual urgency for critical live events without flooding toasts
        }
      },
      onAlert: (alert) => {
        setLiveAlerts((prev) => [alert, ...prev].slice(0, 50));
        const key = alert.alert_id || alert.id;
        if (key && toastGuard.current.has(key)) {
          setStatsTick((t) => t + 1);
          return;
        }
        if (key) {
          toastGuard.current.add(key);
          setTimeout(() => toastGuard.current.delete(key), 15000);
        }
        if (alert.severity === "Critical") {
          toast.error(`Critical alert: ${alert.title}`, { duration: 5500, id: `alert-${key}` });
        } else if (alert.severity === "High") {
          toast.error(`High-risk alert: ${alert.title}`, { duration: 4500, id: `alert-${key}` });
        } else {
          toast(`Alert opened · ${alert.severity}`, { icon: "⚠", id: `alert-${key}` });
        }
        setStatsTick((t) => t + 1);
      },
      onStatus: (status) => {
        if (status?.refresh) {
          setStatsTick((t) => t + 1);
          return;
        }
        simulatorStatusRevision.current += 1;
        setSimStatus(status);
      },
      onError: setLiveError,
    });
    socket.connect();
    return () => {
      active = false;
      socket.disconnect();
    };
  }, []);

  const simulatorRunning = Boolean(simStatus?.is_running);
  const toggleSimulator = useCallback(async () => {
    if (simulatorToggleInFlight.current) return null;

    simulatorToggleInFlight.current = true;
    setSimulatorBusy(true);
    const wasRunning = simulatorRunning;
    try {
      const res = wasRunning ? await api.stopSimulator() : await api.startSimulator();
      simulatorStatusRevision.current += 1;
      setSimStatus(res.data);
      setLiveError(null);
      return { wasRunning, status: res.data };
    } catch (error) {
      setLiveError(error.response?.data?.detail || "Simulator control failed. Check the backend connection.");
      throw error;
    } finally {
      simulatorToggleInFlight.current = false;
      setSimulatorBusy(false);
    }
  }, [simulatorRunning]);

  const value = useMemo(
    () => ({
      connection,
      liveEvents,
      liveAlerts,
      simStatus,
      simulatorRunning,
      simulatorBusy,
      toggleSimulator,
      liveError,
      statsTick,
      setSimStatus,
    }),
    [connection, liveEvents, liveAlerts, simStatus, simulatorRunning, simulatorBusy, liveError, statsTick, toggleSimulator]
  );

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive() {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive must be used within LiveProvider");
  return ctx;
}
