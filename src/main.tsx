import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Gauge,
  Settings,
  ExternalLink,
  Minus,
  Snowflake,
  Droplets,
  Fan,
  Sparkles,
  House,
  Sun,
  Battery,
  Zap,
  Car,
  SlidersHorizontal,
  LayoutGrid,
  Workflow,
  ShieldCheck,
  ArrowUpRight,
  ArrowDownLeft,
  ArrowUpLeft,
  LogIn,
  LogOut,
  RotateCcw,
  Check,
  X,
  Search,
  Power,
  Thermometer,
  Lightbulb,
  Plug,
  ChevronRight,
  CirclePause,
  CircleStop,
  LockKeyhole,
  RefreshCw,
  History,
  Activity,
  Menu,
  Plus,
  LoaderCircle,
  CloudSun,
  Cable,
  WifiOff,
  Moon,
  UserRound,
  Volume2,
  Printer,
  Server,
  ShieldAlert,
  DoorOpen,
  PanelsTopLeft,
  Flame,
  Scale,
  Bot,
  Play,
  Pause,
  VolumeX,
  Wallet,
  Command,
  ArrowUpDown,
} from "lucide-react";
import HomeDashboard from "./HomeDashboard";
import EnergyPolicy from "./EnergyPolicy";
import EnergyEconomics from "./EnergyEconomics";
import EnergyHistory from "./EnergyHistory";
import LocalLogin from "./LocalLogin";
import Tesla from "./Tesla";
import BatteryPanel from "./Battery";
import { EMPTY, type Layout, arrange, move } from "./arrange";
import { ArrangeBar, Sortable, useSortable } from "./ArrangeMode";
import { LOCAL_ROLES, LocalUsers, PasswordChange } from "./LocalUsers";
import {
  Snapshot,
  State,
  Device,
  bindings,
  value,
  number,
  format,
  valid,
  label,
  name,
  devices,
  helpers,
  houseFloors,
  houseRooms,
  inLocation,
  deviceReading,
  controllable,
  controlCategory,
} from "./model";
import Aurora from "./Aurora";
import { auroraMix } from "./aurora-mix";
import CommandPalette, { type PaletteItem } from "./CommandPalette";
import { energyFlow } from "./energy-flow";
import { morph, reveal, useSpotlight } from "./motion";
import "@fontsource-variable/geist/wght.css";
import "@fontsource-variable/geist-mono/wght.css";
import "./style.css";
import "./spatial.css";
import "./theme.css";
import "./nova.css";

const BASE = import.meta.env.BASE_URL;
// Pages are addressed by hash so reload, links and the phone back button keep the page.
const routes: Record<string, string> = {
  overview: "",
  energy: "energie",
  economics: "costuri",
  policy: "politica",
  tesla: "tesla",
  battery: "baterie",
  devices: "dispozitive",
  rules: "automatizari",
  audit: "jurnal",
  settings: "setari",
};
const tabFromHash = () => {
  const slug = decodeURIComponent(location.hash.slice(1));
  return Object.keys(routes).find((key) => slug && routes[key] === slug) || "overview";
};
const hvacModes: Record<string, [string, any]> = {
  off: ["Oprit", Power],
  heat: ["Incalzire", Flame],
  cool: ["Racire", Snowflake],
  dry: ["Uscare", Droplets],
  fan_only: ["Ventilatie", Fan],
  auto: ["Automat", Sparkles],
  heat_cool: ["Incalzire / racire", Sparkles],
};
const pointerFine = () => {
  try { return matchMedia("(pointer: fine)").matches; } catch { return true; }
};
const titles: Record<string, string> = {
  overview: "Privire de ansamblu",
  energy: "Energie",
  policy: "Politica Energie",
  tesla: "Tesla",
  battery: "Baterie",
  economics: "Costuri si prognoza",
  devices: "Dispozitive",
  rules: "Automatizari",
  audit: "Jurnal de comenzi",
  settings: "Acces si configurare",
};
const parts: Record<string, { name: string; sub: string; icon: any }> = {
  battery: {
    name: "Bateria casei",
    sub: "Easyway Energy / 16 kWh",
    icon: Battery,
  },
  solar: {
    name: "Productie solara",
    sub: "15 kWp / toate panourile",
    icon: Sun,
  },
  house: { name: "Consum casa", sub: "Citire din Deye", icon: House },
  inverter: {
    name: "Invertor hibrid",
    sub: "Deye SUN-20K / trifazat",
    icon: Zap,
  },
  grid: { name: "Reteaua electrica", sub: "Import si export", icon: Cable },
  tesla: { name: "Tesla", sub: "Salavat T3", icon: Car },
};
function App() {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem("casa-theme");
      if (saved === "dark" || saved === "light") return saved;
      return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch { return "light"; }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("casa-theme", theme); } catch { /* Storage may be disabled. */ }
  }, [theme]);
  const [data, setData] = useState<Snapshot | null>(null),
    [tab, setTab] = useState(tabFromHash),
    [mode, setMode] = useState<"control" | "configure">("control"),
    [selected, setSelected] = useState("battery"),
    [mobile, setMobile] = useState(false),
    [period, setPeriod] = useState("day");
  const [history, setHistory] = useState<any>(null),
    [historyLoading, setHistoryLoading] = useState(false),
    [chartError, setChartError] = useState(""),
    [loading, setLoading] = useState(true),
    [notice, setNotice] = useState(""),
    [pending, setPending] = useState(false),
    [dialog, setDialog] = useState<any>(null),
    [filter, setFilter] = useState(""),
    [quickQuery, setQuickQuery] = useState(""),
    [area, setArea] = useState("all"),
    [deviceFloor, setDeviceFloor] = useState("all"),
    [audit, setAudit] = useState<any[]>([]),
    [users, setUsers] = useState<any[]>([]),
    [palette, setPalette] = useState(false),
    [layout, setLayout] = useState<Layout>(EMPTY),
    [arrangeInventory, setArrangeInventory] = useState(false);
  const userId = data?.user?.id || "";
  const layoutKey = "casa-layout:" + userId;
  const layoutTimer = React.useRef<number>(0);
  // Order is cached per account for an instant first paint; the server copy wins.
  useEffect(() => {
    if (!userId) return;
    try { const cached = localStorage.getItem(layoutKey); if (cached) setLayout({ ...EMPTY, ...JSON.parse(cached) }); } catch { /* storage off */ }
    fetch(BASE + "api/layout").then((r) => (r.ok ? r.json() : null)).then((saved) => saved && setLayout({ ...EMPTY, ...saved })).catch(() => {});
  }, [userId]);
  useEffect(() => { if (userId) try { localStorage.setItem(layoutKey, JSON.stringify(layout)); } catch { /* storage off */ } }, [layout, userId]);
  const refreshUsage = () => fetch(BASE + "api/layout").then((r) => (r.ok ? r.json() : null)).then((saved) => saved && setLayout((now) => ({ ...now, usage: saved.usage || {}, usage_days: saved.usage_days }))).catch(() => {});
  const changeLayout = (change: Partial<Layout>) => setLayout((now) => {
    const next = { ...now, ...change };
    clearTimeout(layoutTimer.current);
    layoutTimer.current = window.setTimeout(() => {
      post("layout", { sort: next.sort, order: next.order, groups: next.groups }).catch((e) => setNotice(e.message));
    }, 400);
    return next;
  });
  useSpotlight();
  // The theme opens as a circle from the pressed control (View Transitions, where available).
  const switchTheme = (next: string, origin: { clientX: number; clientY: number } | null) => {
    if (next === theme) return;
    reveal(origin, () => { document.documentElement.dataset.theme = next; setTheme(next); });
  };
  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") { event.preventDefault(); setPalette((open) => !open); }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, []);
  const role = data?.user?.role || "viewer";
  const canControl = !!data?.connected && role !== "viewer",
    canConfigure =
      !!data?.connected && role === "configure" && mode === "configure";
  const paused = data?.states[bindings.pause]?.state === "on";
  const adminMode = role === "configure" && mode === "configure";
  // Casa-only accounts can have the Parametri role (configure) but never HA administration.
  const localAccount = !!data?.user?.local;
  const haAdmin = data?.user?.admin ?? (role === "configure" && !localAccount);
  const roleName = localAccount ? LOCAL_ROLES[role] || "Vizualizare" : role === "configure" ? "Administrator" : role === "control" ? "User" : "Vizualizare";
  const go = (view: string, replace = false) => {
    if (view !== tab) morph(() => setTab(view)); else setTab(view);
    const url = routes[view] ? "#" + routes[view] : location.pathname + location.search;
    if (tabFromHash() !== view || (!routes[view] && location.hash))
      window.history[replace ? "replaceState" : "pushState"](null, "", url);
  };
  useEffect(() => {
    const sync = () => { morph(() => setTab(tabFromHash())); setMobile(false); };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [tab]);
  useEffect(() => {
    if (role !== "configure") {
      setMode("control");
      setUsers([]);
    }
    if ((role !== "configure" || !haAdmin) && tab === "audit") go("overview", true);
  }, [role, tab, haAdmin]);
  useEffect(() => {
    let source: EventSource | undefined;
    let alive = true;
    fetch(BASE + "api/session")
      .then(async (r) => {
        if (r.status === 401) return;
        if (!r.ok) throw Error("Conectarea la HA nu este disponibila.");
        const initial = await r.json();
        if (!alive) return;
        setData(initial);
        source = new EventSource(BASE + "api/events");
        source.onmessage = (e) => {
          if (!alive) return;
          const packet = JSON.parse(e.data);
          if (packet.type === "delta")
            setData((previous) => {
              if (!previous) return previous;
              const states = { ...previous.states };
              for (const [id, state] of Object.entries(packet.states)) {
                if (state === null) delete states[id];
                else states[id] = state as State;
              }
              return {
                ...previous,
                states,
                connected: packet.connected,
                last_update: packet.last_update,
              };
            });
          else setData(packet);
        };
        source.onerror = () => {
          if (alive) setData((d) => (d ? { ...d, connected: false } : null));
        };
      })
      .catch((e) => setNotice(e.message))
      .finally(() => setLoading(false));
    return () => {
      alive = false;
      source?.close();
    };
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!data) return;
    const control = new AbortController();
    // The previous chart stays visible, dimmed, until the new period arrives.
    setHistoryLoading(true);
    setChartError("");
    fetch(BASE + "api/history?period=" + period, { signal: control.signal })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw Error(body.error || "Istoricul nu este disponibil.");
        return body;
      })
      .then((body) => setHistory({ ...body, period: body.period || period }))
      .catch((e) => {
        if (e.name !== "AbortError") {
          setHistory(null);
          setChartError(e.message);
        }
      })
      .finally(() => {
        if (!control.signal.aborted) setHistoryLoading(false);
      });
    return () => control.abort();
  }, [period, !!data]);
  useEffect(() => {
    if (!data || role !== "configure" || mode !== "configure" || !haAdmin) return;
    if (tab === "audit")
      fetch(BASE + "api/audit")
        .then((r) => (r.ok ? r.json() : []))
        .then(setAudit);
    if (tab === "settings")
      fetch(BASE + "api/users")
        .then((r) => (r.ok ? r.json() : []))
        .then(setUsers);
  }, [tab, role, mode, !!data, haAdmin]);
  useEffect(() => {
    if (!dialog) return;
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !pending) setDialog(null);
    };
    window.addEventListener("keydown", close);
    const previous = document.activeElement as HTMLElement;
    const timer = setTimeout(
      () => {
        const modal = document.querySelector<HTMLElement>('[role="dialog"]');
        if (modal && !modal.contains(document.activeElement))
          modal.querySelector<HTMLElement>('input:not(:disabled), select:not(:disabled), button:not(:disabled)')?.focus();
      },
      30,
    );
    return () => {
      window.removeEventListener("keydown", close);
      clearTimeout(timer);
      previous?.focus();
    };
  }, [!!dialog, pending]);
  async function post(path: string, body: any) {
    const r = await fetch(BASE + "api/" + path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": data?.csrf || "",
      },
      body: JSON.stringify(body),
    });
    const result = await r.json();
    if (!r.ok) throw Error(result.error || "Cererea a fost refuzata.");
    return result;
  }
  const navigate = (view: string, room?: string, floor?: string) => {
    go(view);
    setMobile(false);
    if (room !== undefined) { setArea(room); setFilter(""); }
    if (floor !== undefined) setDeviceFloor(floor);
  };
  const s = (key: string) => data?.states[(data?.bindings || bindings)[key]];
  const ask = (entity_id: string, action: string, v: any, title: string) =>
    setDialog({ kind: "command", entity_id, action, value: v, title });
  // Owner decision 2026-11-10: lights act on the first press, without a confirmation
  // dialog. Climate, boiler, sockets and everything else still ask. The switch moves only
  // when HA reports the new state (no optimistic state); the server checks role and limits.
  const [sending, setSending] = useState<Record<string, true>>({});
  const isLight = (entity_id: string) => entity_id.startsWith("light.") || allDevices.some((d) => d.primary.entity_id === entity_id && controlCategory(d) === "lights");
  async function send(entity_id: string, action: string, v?: any) {
    if (sending[entity_id]) return;
    setSending((now) => ({ ...now, [entity_id]: true }));
    try {
      await post("command", { entity_id, action, ...(v !== undefined ? { value: v } : {}) });
      try { navigator.vibrate?.(12); } catch { /* no haptics */ }
    } catch (e: any) {
      setNotice(e.message);
    } finally {
      setSending((now) => { const next = { ...now }; delete next[entity_id]; return next; });
    }
  }
  async function confirm() {
    setPending(true);
    try {
      await post("command", {
        entity_id: dialog.entity_id,
        action: dialog.action,
        ...(dialog.value !== undefined ? { value: dialog.value } : {}),
      });
      setNotice(
        "Comanda acceptata de HA. Starea se actualizeaza la confirmare.",
      );
      setDialog(null);
    } catch (e: any) {
      setNotice(e.message);
    } finally {
      setPending(false);
    }
  }
  const entityControl = (state: State) => {
    const domain = state.entity_id.split(".")[0],
      unavailable = !canControl || !valid(state) || pending;
    if (["switch", "light", "fan"].includes(domain))
      return (
        <button
          className={"toggle" + (sending[state.entity_id] ? " busy" : "")}
          role="switch"
          aria-label={name(state)}
          aria-checked={state.state === "on"}
          aria-busy={!!sending[state.entity_id]}
          disabled={unavailable}
          onClick={() =>
            isLight(state.entity_id) ? send(state.entity_id, state.state === "on" ? "turn_off" : "turn_on") : ask(
              state.entity_id,
              state.state === "on" ? "turn_off" : "turn_on",
              undefined,
              `${state.state === "on" ? "Opresti" : "Pornesti"} ${name(state)}?`,
            )
          }
        />
      );
    if (["climate", "water_heater"].includes(domain))
      return (
        <span className="inline-controls">
        {state.entity_id === "water_heater.boiler" && data?.states["switch.boiler_ariston_power"] && entityControl(data.states["switch.boiler_ariston_power"])}
        <button
          className="icon-button"
          title="Temperatura"
          aria-label={"Temperatura " + name(state)}
          disabled={
            unavailable ||
            ["climate.heat", "climate.bedroom_heat"].includes(state.entity_id)
          }
          onClick={() =>
            setDialog({
              kind: "temperature",
              entity: state,
              value:
                state.attributes.temperature ||
                state.attributes.current_temperature,
              title: name(state),
            })
          }
        >
          <SlidersHorizontal size={18} />
        </button>
        </span>
      );
    if (domain === "media_player") {
      const features = Number(state.attributes.supported_features || 0), playing = state.state === "playing", off = state.state === "off";
      return <span className="inline-controls">
        {(features & (off ? 128 : 256)) !== 0 && <button className="icon-button" title={off ? "Porneste media" : "Opreste media"} aria-label={(off ? "Porneste " : "Opreste ") + name(state)} disabled={unavailable} onClick={() => ask(state.entity_id, off ? "turn_on" : "turn_off", undefined, `${off ? "Pornesti" : "Opresti"} ${name(state)}?`)}><Power size={17}/></button>}
        {(features & (playing ? 1 : 16384)) !== 0 && <button className="icon-button" title={playing ? "Pauza" : "Redare"} aria-label={(playing ? "Pauza " : "Redare ") + name(state)} disabled={unavailable} onClick={() => ask(state.entity_id, playing ? "media_pause" : "media_play", undefined, `${playing ? "Pui pe pauza" : "Reiei redarea pe"} ${name(state)}?`)}>{playing ? <Pause size={17}/> : <Play size={17}/>}</button>}
        {(features & 4) !== 0 && <button className="icon-button" title="Volum" aria-label={"Volum " + name(state)} disabled={unavailable} onClick={() => setDialog({kind:"volume",entity:state,value:Math.round(Math.max(0, Math.min(1, Number(state.attributes.volume_level) || 0)) * 100),title:name(state)})}><Volume2 size={17}/></button>}
      </span>;
    }
    return null;
  };
  const stats = (energy = false) => (
    <div className="metrics">
      {(energy
        ? [
            ["solarToday", "Solar astazi", Sun, "kWh", "solar"],
            ["loadToday", "Consum astazi", House, "kWh", "load"],
            ["forecast", "Prognoza maine", CloudSun, "kWh", "battery"],
            ["soc", "Nivel baterie", Battery, "%", "battery"],
          ]
        : [
            ["solar", "Productie solara", Sun, "kW", "solar"],
            ["load", "Consum casa", House, "kW", "load"],
            ["soc", "Baterie", Battery, "%", "battery"],
            ["import", "Import retea", ArrowDownLeft, "kW", "grid"],
          ]
      ).map(([key, title, Icon, u, color]: any) => (
        <button
          key={key}
          className={"metric " + color}
          onClick={() =>
            setSelected(
              key === "soc"
                ? "battery"
                : key === "import"
                  ? "grid"
                  : key === "load"
                    ? "house"
                    : "solar",
            )
          }
        >
          <span className="metric-label">
            <Icon size={17} />
            {title}
          </span>
          <strong>
            {format(value(data, key))}
            <small>{u}</small>
          </strong>
          <span className="metric-detail">
            {key === "soc"
              ? `${format(value(data, "discharge"))} kW descarcare`
              : key === "import"
                ? `${format(value(data, "export"))} kW export`
                : key === "solar"
                  ? `${format(value(data, "solarToday"))} kWh astazi`
                  : key === "load"
                    ? `${format(value(data, "loadToday"))} kWh astazi`
                    : "Home Assistant"}
          </span>
        </button>
      ))}
    </div>
  );
  const field = (id: string) => {
    const state = data?.states[id];
    return (
      <div key={id} className="setting-row">
        <div>
          <span>{helpers[id] || name(state)}</span>
          <small>{state ? label(state) : "Fara date"}</small>
        </div>
        <button
          className="icon-button"
          title={"Modifica " + (helpers[id] || name(state))}
          aria-label={"Modifica " + (helpers[id] || name(state))}
          disabled={!canConfigure || !valid(state)}
          onClick={() =>
            setDialog({
              kind: "parameter",
              entity: state,
              value: state!.state,
              title: helpers[id] || name(state),
            })
          }
        >
          <SlidersHorizontal size={17} />
        </button>
      </div>
    );
  };
  function inspector() {
    const part = parts[selected] || parts.battery,
      Icon = part.icon;
    const rows =
      selected === "battery"
        ? [
            ["soc", "Nivel incarcare", "%"],
            ["batteryTemp", "Temperatura", "°C"],
            ["charge", "Putere incarcare", "kW"],
            ["discharge", "Putere descarcare", "kW"],
            ["limit", "Limita recomandata", "kW"],
            ["reserve", "Rezerva recomandata", "%"],
          ]
        : selected === "grid"
          ? [
              ["import", "Din retea", "kW"],
              ["export", "Injectie", "kW"],
            ]
          : selected === "solar"
            ? [
                ["solar", "Productie totala", "kW"],
                ["solarToday", "Produs astazi", "kWh"],
                ["forecast", "Prognoza maine", "kWh"],
              ]
            : selected === "tesla"
              ? [["tesla", "Putere incarcare", "kW"]]
              : [
                  ["load", "Consum casa", "kW"],
                  ["solar", "Productie totala", "kW"],
                  ["import", "Din retea", "kW"],
                ];
    return (
      <aside className="inspector">
        <div className="inspector-title">
          <span className="object-icon">
            <Icon size={25} />
          </span>
          <span>
            <h2>{part.name}</h2>
            <small>{part.sub}</small>
          </span>
        </div>
        <div className={"status-label " + (data?.connected ? "good" : "muted")}>
          <span className="status-dot" />
          {data?.connected
            ? "Conexiune HA activa"
            : data
              ? "HA deconectat"
              : "Autentificare necesara"}
        </div>
        {selected === "battery" && (
          <div className="battery-readout">
            <strong>
              {format(value(data, "soc"), 0)}
              <small>%</small>
            </strong>
            <div className="charge-bar">
              <span
                style={{
                  width:
                    Math.max(0, Math.min(100, value(data, "soc") || 0)) + "%",
                }}
              />
            </div>
          </div>
        )}
        <dl className="readouts">
          {rows.map(([key, title, u]) => (
            <div key={key}>
              <dt>{title}</dt>
              <dd>
                {format(value(data, key))}
                <small>{u}</small>
              </dd>
            </div>
          ))}
        </dl>
        {selected === "battery" && (
          <>
            <div className="section-title">
              <h3>Politica bateriei</h3>
              <ShieldCheck size={16} />
            </div>
            <div className="policy-status">
              <span className="status-dot" />
              {paused
                ? "Automatizari in pauza"
                : s("manager")?.state === "on"
                  ? "Management automat"
                  : "Control manual"}
            </div>
            {[
              "input_number.deye_battery_min_soc",
              "input_number.deye_battery_max_discharge_kw",
            ].map(field)}
            <button
              className="text-button"
              onClick={() => navigate("settings")}
            >
              Toate setarile <ArrowUpRight size={16} />
            </button>
          </>
        )}
        {selected === "solar" && (
          <div className="technical-note">
            15 kWp instalati<span>9 kWp SV / 6 kWp NE</span>
            <span>Inclinatie estimata: 30°</span>
          </div>
        )}
        {selected === "grid" && (
          <div className="technical-note">
            Tarife actuale<span>Import: {format(number(data?.states['sensor.home_energy_import_price']),2)} lei/kWh</span>
            <span>Export: {format(number(data?.states['sensor.home_energy_export_price']),2)} lei/kWh</span>
          </div>
        )}
        {selected === "tesla" && (
          <button className="text-button" onClick={() => navigate("devices")}>
            Dispozitive Tesla <ChevronRight size={16} />
          </button>
        )}
      </aside>
    );
  }
  const chart = () => (
    <EnergyHistory
      authenticated={!!data}
      history={history}
      loading={historyLoading}
      error={chartError}
      period={period}
      onPeriod={setPeriod}
    />
  );
  const allDevices = devices(data),
    shown = allDevices.filter(
      (d) =>
        inLocation(d, deviceFloor, area) &&
        `${d.name} ${d.manufacturer} ${d.floor} ${d.area}`
          .toLowerCase()
          .includes(filter.toLowerCase()),
    );
  const inventorySorter = useSortable((ids, id, to) => changeLayout({ sort: "manual", order: move(layout.sort === "manual" ? layout.order : arrange(allDevices, layout).map((d) => d.id), ids, id, to) }));
  const usesOf = (d: Device) => Object.entries(layout.usage).reduce((n, [entity, count]) => n + (d.primary.entity_id === entity || d.entries.some((e) => e.entity_id === entity) ? count : 0), 0);
  const loginButton = (
    <div className="login-choices">
      <a className="button primary" href={BASE + "auth/login"}>
        <LogIn size={17} />
        Conectare cu Home Assistant
      </a>
      <button className="button" onClick={() => setDialog({ kind: "local-login", title: "Conectare cu cont Casa" })}>
        <UserRound size={17} />
        Cont Casa
      </button>
    </div>
  );
  function deviceCard(d: Device) {
    const p = d.primary,
      dom = p.entity_id.split(".")[0],
      Icon = ({light: Lightbulb, climate: Thermometer, water_heater: Flame, media_player: Volume2, printer: Printer, nas: Server, vacuum: Bot, alarm_control_panel: ShieldAlert, door: DoorOpen, window: PanelsTopLeft, smoke: Flame, weight: Scale, car: Car, charger: Cable, energy: Zap, battery: Battery} as Record<string, any>)[d.kind] || Plug;
    const corrected =
      p.entity_id === "climate.bedroom_heat"
        ? data?.states["sensor.hvac_upstairs_temperature"]
        : p.entity_id === "climate.heat"
          ? data?.states["sensor.hvac_downstairs_temperature"]
          : undefined;
    return (
      <article
        className={"device-card " + (d.pending ? "pending-device" : !valid(p) ? "unavailable" : ((d.kind === "smoke" && p.state === "on") || p.state === "triggered") ? "device-alert" : "")}
        key={d.id}
      >
        <div className="device-top">
          <span
            className={
              "device-icon " +
              (p.state === "on" || p.attributes.hvac_action === "heating"
                ? "active"
                : "")
            }
          >
            <Icon size={23} />
          </span>
          <small>{d.floor}<br/>{d.area}</small>
        </div>
        <h3>{d.name}</h3>
        <span className="device-description">{d.manufacturer || dom}</span>
        {d.note && <span className="device-note">{d.note}</span>}
        {d.ratedPower !== undefined && <span className="device-note">Putere nominala: {format(d.ratedPower)} kW</span>}
        {d.id === "boiler" && <dl className="device-live-details"><div><dt>Rezistenta</dt><dd>{data?.states["binary_sensor.boiler_ariston_is_heating"]?.state === "on" ? "Incalzeste" : data?.states["binary_sensor.boiler_ariston_is_heating"]?.state === "off" ? "In repaus" : "Fara date"}</dd></div><div><dt>Consum estimat</dt><dd>{format(value(data, "boiler"))} kW</dd></div><div><dt>Temperatura tinta</dt><dd>{p.attributes.temperature ?? "--"} °C</dd></div></dl>}
        <div className="device-bottom">
          <span>
            <i className={"status-dot " + (!valid(p) ? "offline" : "")} />
            {d.pending ? deviceReading(d) : corrected
              ? label(corrected)
              : p.attributes.current_temperature !== undefined
                ? `${format(number({ state: String(p.attributes.current_temperature), entity_id: "", attributes: {} }))} °C`
                : deviceReading(d)}
          </span>
          {!d.pending && entityControl(p)}
        </div>
      </article>
    );
  }
  function rules() {
    const rules = Object.values(data?.states || {}).filter(
      (s) =>
        s.entity_id.startsWith("automation.") &&
        s.entity_id !== "automation.ha_global_automation_killswitch_controller",
    );
    return (
      <section className="page-section">
        <div className="section-top">
          <div>
            <span className="eyebrow">HOME ASSISTANT</span>
            <h2>Regulile casei</h2>
          </div>
          {canConfigure && (
            <button
              className="button primary"
              onClick={() =>
                setDialog({
                  kind: "rule",
                  title: "Regula noua",
                  form: {
                    name: "",
                    trigger: "time",
                    at: "18:00",
                    event: "sunset",
                    offset: 15,
                    entity_id: "",
                    action: "turn_on",
                    value: 0,
                    source: "",
                    threshold: 2,
                    comparator: "above",
                    hold: 60,
                  },
                })
              }
            >
              <Plus size={17} />
              Regula noua
            </button>
          )}
        </div>
        {!data ? (
          <div className="empty-state">
            <LockKeyhole />
            {loginButton}
          </div>
        ) : (
          <div className="rule-list">
            {rules.map((r) => (
              <div className="rule-row" key={r.entity_id}>
                <span
                  className={"rule-icon " + (r.state === "on" ? "active" : "")}
                >
                  <Workflow size={19} />
                </span>
                <div>
                  <strong>{name(r)}</strong>
                  <small>
                    {r.attributes.last_triggered
                      ? "Ultima executie: " +
                        new Date(r.attributes.last_triggered).toLocaleString(
                          "ro-RO",
                          { timeZone: "Europe/Bucharest" },
                        )
                      : "Fara executii inregistrate"}
                  </small>
                </div>
                <button
                  className="toggle"
                  role="switch"
                  aria-label={name(r)}
                  aria-checked={r.state === "on"}
                  disabled={!canConfigure || pending}
                  onClick={() =>
                    ask(
                      r.entity_id,
                      r.state === "on" ? "turn_off" : "turn_on",
                      undefined,
                      `${r.state === "on" ? "Opresti" : "Activezi"} ${name(r)}?`,
                    )
                  }
                />
              </div>
            ))}
          </div>
        )}
      </section>
    );
  }
  function modal() {
    if (!dialog) return null;
    const d = dialog;
    if (d.kind === "local-login") return <LocalLogin onClose={() => setDialog(null)} />;
    const set = (patch: any) => setDialog({ ...d, ...patch });
    const setForm = (patch: any) => set({ form: { ...d.form, ...patch } });
    return (
      <div
        className="modal-shade"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget && !pending) setDialog(null);
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
          className="modal"
          onKeyDown={(e) => {
            if (e.key !== "Tab") return;
            const items = [
              ...e.currentTarget.querySelectorAll<HTMLElement>(
                "button:not(:disabled),input,select,a[href]",
              ),
            ];
            if (e.shiftKey && document.activeElement === items[0]) {
              e.preventDefault();
              items.at(-1)?.focus();
            } else if (!e.shiftKey && document.activeElement === items.at(-1)) {
              e.preventDefault();
              items[0]?.focus();
            }
          }}
        >
          <header>
            <h2 id="modal-title">{d.title}</h2>
            <button
              className="icon-button"
              title="Inchide"
              aria-label="Inchide"
              disabled={pending}
              onClick={() => setDialog(null)}
            >
              <X size={20} />
            </button>
          </header>
          <div className="modal-body">
            {d.kind === "sessions" ? (
              <p>Se inchid toate sesiunile Casa ale contului tau: telefon, tableta si browsere, inclusiv aceasta. Home Assistant, aplicatia HA si automatizarile nu sunt afectate. Te conectezi din nou cu contul HA.</p>
            ) : d.kind === "command" ? (
              <p>
                {d.entity_id === bindings.pause
                  ? d.action === "turn_on"
                    ? "Se opresc automatizarile casei. Backupurile continua. Dispozitivele raman in starea actuala."
                    : "Dupa un restart, automatizarile trebuie activate individual."
                  : d.value !== undefined
                    ? `${name(data?.states[d.entity_id])}: ${d.value} ${data?.states[d.entity_id]?.attributes.unit_of_measurement || ""}`
                    : name(data?.states[d.entity_id])}
              </p>
            ) : d.kind === "volume" ? (
              <><label className="field">Volum <output>{d.value}%</output><input type="range" aria-label="Volum media" min="0" max="100" step="1" value={d.value} onChange={event => set({value:Number(event.target.value)})}/></label>{(Number(d.entity.attributes.supported_features || 0) & 8) !== 0 && <button className="button media-mute" onClick={() => ask(d.entity.entity_id, "set_mute", d.entity.attributes.is_volume_muted ? "off" : "on", `${d.entity.attributes.is_volume_muted ? "Reactivezi" : "Opresti"} sunetul pe ${name(d.entity)}?`)}>{d.entity.attributes.is_volume_muted ? <Volume2 size={17}/> : <VolumeX size={17}/>} {d.entity.attributes.is_volume_muted ? "Reactiveaza sunetul" : "Fara sunet"}</button>}</>
            ) : d.kind === "parameter" || d.kind === "temperature" ? (() => {
              const attrs = d.entity.attributes;
              const step = Number(attrs.step || attrs.target_temp_step || 0.5) || 0.5;
              const limit = (v: any) => (v === undefined || v === null || v === "" || !Number.isFinite(Number(v)) ? null : Number(v));
              const min = limit(d.kind === "temperature" ? attrs.min_temp : attrs.min);
              const max = limit(d.kind === "temperature" ? attrs.max_temp : attrs.max);
              const unitText = d.kind === "temperature" ? "°C" : attrs.unit_of_measurement || "";
              const current = Number(d.value);
              const nudge = (direction: number) => {
                const base = Number.isFinite(current) && String(d.value).trim() !== "" ? current : (min ?? 0);
                let next = Math.round((base + direction * step) / step) * step;
                if (min !== null) next = Math.max(min, next);
                if (max !== null) next = Math.min(max, next);
                set({ value: String(Number(next.toFixed(3))) });
              };
              const mode = hvacModes[d.entity.state]?.[0];
              return (
              <>
                {d.kind === "temperature" && (
                  <p className="dialog-context">
                    {attrs.current_temperature !== undefined && attrs.current_temperature !== null && (
                      <span><Thermometer size={15} />Acum {format(limit(attrs.current_temperature), 1)} °C</span>
                    )}
                    <span><Activity size={15} />{mode || label(d.entity)}</span>
                  </p>
                )}
                <label className="field">
                  {d.kind === "temperature"
                    ? "Temperatura dorita"
                    : helpers[d.entity.entity_id] || name(d.entity)}
                  <div className="stepper">
                    <button
                      type="button"
                      className="stepper-button"
                      aria-label="Scade valoarea"
                      title="Scade valoarea"
                      disabled={min !== null && Number.isFinite(current) && current <= min}
                      onClick={() => nudge(-1)}
                    >
                      <Minus size={20} />
                    </button>
                    <div className="input-unit">
                      <input
                        autoFocus={pointerFine()}
                        aria-label="Valoare"
                        type="number"
                        inputMode="decimal"
                        step={step}
                        min={min ?? undefined}
                        max={max ?? undefined}
                        value={d.value}
                        onChange={(e) => set({ value: e.target.value })}
                      />
                      <span>{unitText}</span>
                    </div>
                    <button
                      type="button"
                      className="stepper-button"
                      aria-label="Creste valoarea"
                      title="Creste valoarea"
                      disabled={max !== null && Number.isFinite(current) && current >= max}
                      onClick={() => nudge(1)}
                    >
                      <Plus size={20} />
                    </button>
                  </div>
                  {(min !== null || max !== null) && (
                    <small className="field-hint">
                      Interval permis {min !== null ? format(min, 2) : "--"} - {max !== null ? format(max, 2) : "--"} {unitText}, pas {format(step, 2)}
                    </small>
                  )}
                </label>
                {d.kind === "temperature" &&
                  d.entity.entity_id.startsWith("climate.") &&
                  (attrs.hvac_modes || []).length > 0 && (
                    <div className="mode-options" role="group" aria-label="Mod de functionare">
                      {(attrs.hvac_modes || []).map((m: string) => {
                        const [title, ModeIcon] = hvacModes[m] || [m, Activity];
                        return (
                          <button
                            key={m}
                            className={"mode-chip " + m + (d.entity.state === m ? " selected" : "")}
                            aria-pressed={d.entity.state === m}
                            onClick={() =>
                              ask(
                                d.entity.entity_id,
                                "set_hvac_mode",
                                m,
                                `Setezi ${name(d.entity)} pe ${title.toLowerCase()}?`,
                              )
                            }
                          >
                            <ModeIcon size={17} />
                            {title}
                          </button>
                        );
                      })}
                    </div>
                  )}
                {d.kind === "temperature" && d.entity.entity_id.startsWith("climate.") && d.entity.attributes.fan_modes?.length > 0 && <label className="field">Ventilator<select aria-label="Treapta ventilator" value={d.entity.attributes.fan_mode || ""} onChange={event => ask(d.entity.entity_id, "set_fan_mode", event.target.value, `Setezi ventilatorul ${name(d.entity)} pe ${event.target.value}?`)}>{!d.entity.attributes.fan_mode && <option value="" disabled>Neconfirmat</option>}{d.entity.attributes.fan_modes.map((fan: string) => <option key={fan} value={fan}>{fan}</option>)}</select></label>}
                {d.kind === "temperature" && d.entity.entity_id.startsWith("water_heater.") && <label className="field boiler-mode-field">Mod boiler<select aria-label="Mod boiler" value={d.entity.state} onChange={event => ask(d.entity.entity_id, "set_operation_mode", event.target.value, `Setezi ${name(d.entity)} pe ${event.target.value}?`)}>{(d.entity.attributes.operation_list || []).map((operation: string) => <option key={operation} value={operation}>{operation}</option>)}</select></label>}
              </>
              );
            })() : d.kind === "rule" ? (
              <div className="form-grid">
                <label className="field full">
                  Nume
                  <input
                    value={d.form.name}
                    onChange={(e) => setForm({ name: e.target.value })}
                  />
                </label>
                <label className="field">
                  Declansator
                  <select
                    value={d.form.trigger}
                    onChange={(e) => setForm({ trigger: e.target.value })}
                  >
                    <option value="time">Ora</option>
                    <option value="sun">Rasarit / apus</option>
                    <option value="numeric">Prag senzor</option>
                  </select>
                </label>
                {d.form.trigger === "time" ? (
                  <label className="field">
                    Ora
                    <input
                      type="time"
                      value={d.form.at}
                      onChange={(e) => setForm({ at: e.target.value })}
                    />
                  </label>
                ) : d.form.trigger === "sun" ? (
                  <>
                    <label className="field">
                      Eveniment
                      <select
                        value={d.form.event}
                        onChange={(e) => setForm({ event: e.target.value })}
                      >
                        <option value="sunset">Apus</option>
                        <option value="sunrise">Rasarit</option>
                      </select>
                    </label>
                    <label className="field">
                      Decalaj (minute)
                      <input
                        type="number"
                        min="-180"
                        max="180"
                        value={d.form.offset}
                        onChange={(e) =>
                          setForm({ offset: Number(e.target.value) })
                        }
                      />
                    </label>
                  </>
                ) : (
                  <>
                    <label className="field">
                      Senzor
                      <select
                        value={d.form.source}
                        onChange={(e) => setForm({ source: e.target.value })}
                      >
                        <option value="">Selecteaza</option>
                        {Object.values(data?.states || {})
                          .filter(
                            (s) =>
                              s.entity_id.startsWith("sensor.") &&
                              number(s) !== null,
                          )
                          .map((s) => (
                            <option key={s.entity_id} value={s.entity_id}>
                              {name(s)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className="field">
                      Comparatie
                      <select
                        value={d.form.comparator}
                        onChange={(e) =>
                          setForm({ comparator: e.target.value })
                        }
                      >
                        <option value="above">Mai mare decat</option>
                        <option value="below">Mai mic decat</option>
                      </select>
                    </label>
                    <label className="field">
                      Prag
                      <input
                        type="number"
                        value={d.form.threshold}
                        onChange={(e) =>
                          setForm({ threshold: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label className="field">
                      Durata stabila (secunde)
                      <input
                        type="number"
                        min="0"
                        max="3600"
                        value={d.form.hold}
                        onChange={(e) =>
                          setForm({ hold: Number(e.target.value) })
                        }
                      />
                    </label>
                  </>
                )}
                <label className="field full">
                  Dispozitiv
                  <select
                    value={d.form.entity_id}
                    onChange={(e) =>
                      setForm({
                        entity_id: e.target.value,
                        action: ["climate.", "water_heater."].some((p) =>
                          e.target.value.startsWith(p),
                        )
                          ? "set_temperature"
                          : "turn_on",
                      })
                    }
                  >
                    <option value="">Selecteaza</option>
                    {allDevices
                      .filter((d) =>
                        [
                          "light",
                          "switch",
                          "fan",
                          "climate",
                          "water_heater",
                        ].includes(d.primary.entity_id.split(".")[0]),
                      )
                      .map((d) => (
                        <option key={d.id} value={d.primary.entity_id}>
                          {d.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="field">
                  Actiune
                  <select
                    value={d.form.action}
                    onChange={(e) => setForm({ action: e.target.value })}
                  >
                    {["climate.", "water_heater."].some((p) =>
                      d.form.entity_id.startsWith(p),
                    ) ? (
                      <option value="set_temperature">
                        Seteaza temperatura
                      </option>
                    ) : (
                      <>
                        <option value="turn_on">Porneste</option>
                        <option value="turn_off">Opreste</option>
                      </>
                    )}
                  </select>
                </label>
                {d.form.action === "set_temperature" && (
                  <label className="field">
                    Temperatura
                    <input
                      type="number"
                      value={d.form.value}
                      onChange={(e) =>
                        setForm({ value: Number(e.target.value) })
                      }
                    />
                  </label>
                )}
              </div>
            ) : null}
          </div>
          <footer>
            <button
              className="button"
              disabled={pending}
              onClick={() => setDialog(null)}
            >
              Anuleaza
            </button>
            <button
              className="button primary"
              disabled={pending}
              onClick={async () => {
                if (d.kind === "command") {
                  await confirm();
                  return;
                }
                setPending(true);
                try {
                  if (d.kind === "sessions") {
                    await post("logout-all", {});
                    location.reload();
                    return;
                  }
                  if (d.kind === "rule") {
                    await post("rules", d.form);
                    setNotice("Regula a fost salvata oprita in HA.");
                  } else {
                    await post("command", {
                      entity_id: d.entity.entity_id,
                      action:
                        d.kind === "volume"
                          ? "set_volume"
                          : d.kind === "temperature"
                          ? "set_temperature"
                          : "set_value",
                      value: Number(d.value),
                    });
                    setNotice("Comanda acceptata de HA.");
                  }
                  setDialog(null);
                } catch (e: any) {
                  setNotice(e.message);
                } finally {
                  setPending(false);
                }
              }}
            >
              {pending ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <Check size={16} />
              )}{" "}
              {d.kind === "rule" ? "Salveaza oprita" : d.kind === "sessions" ? "Deconecteaza tot" : "Confirma"}
            </button>
          </footer>
        </div>
      </div>
    );
  }
  // Pages, devices and actions offered by the command palette (Ctrl/Cmd+K).
  const paletteItems = (): PaletteItem[] => [
    ...([["overview", "Acasa", House], ["energy", "Energie", Zap], ["economics", "Costuri si prognoza", Wallet], ["policy", "Politica Energie", Gauge], ["tesla", "Tesla", Car], ["battery", "Baterie", Battery],
      ["devices", "Dispozitive", LayoutGrid], ["rules", "Automatizari", Workflow], ["settings", "Setari", Settings],
      ...(adminMode && haAdmin ? [["audit", "Jurnal", History]] : [])] as any[]).map(([key, title, icon]) => (
      { id: "page-" + key, group: "Pagini", title, icon, always: true, run: () => navigate(key) })),
    { id: "theme", group: "Actiuni", title: theme === "dark" ? "Aspect luminos" : "Aspect intunecat", icon: theme === "dark" ? Sun : Moon,
      keywords: "tema dark light noapte zi culori", always: true, run: () => switchTheme(theme === "dark" ? "light" : "dark", null) },
    ...(role === "configure" ? [{ id: "mode", group: "Actiuni", title: adminMode ? "Revino la modul User" : "Activeaza modul Admin", icon: ShieldCheck,
      keywords: "administrare configurare", always: true, run: () => { setMode(adminMode ? "control" : "configure"); if (tab === "audit") go("overview", true); } }] : []),
    ...allDevices.filter(controllable).flatMap((d): PaletteItem[] => {
      const state = d.primary, domain = state.entity_id.split(".")[0], on = state.state === "on";
      const placed = !!d.area && d.area !== "Fara camera", place = placed ? d.floor + " / " + d.area : "Fara camera";
      const show: PaletteItem = { id: "device-" + d.id, group: "Dispozitive", title: d.name, hint: place + " · " + deviceReading(d), icon: ({ lights: Lightbulb, climate: Thermometer, water: Flame, media: Volume2, mobility: Car } as Record<string, any>)[controlCategory(d)] || Plug,
        keywords: d.manufacturer, run: () => navigate("overview", placed ? d.area : "all", placed ? d.floor : "all") };
      // Same behaviour as the switch on the page: lights act directly, the rest ask.
      return ["switch", "light", "fan"].includes(domain) && canControl && valid(state) && !pending
        ? [show, { id: "command-" + d.id, group: "Comenzi", title: (on ? "Opreste " : "Porneste ") + d.name, hint: isLight(state.entity_id) ? "direct" : "cere confirmare", icon: Power,
            run: () => isLight(state.entity_id) ? send(state.entity_id, on ? "turn_off" : "turn_on") : ask(state.entity_id, on ? "turn_off" : "turn_on", undefined, (on ? "Opresti " : "Pornesti ") + d.name + "?") }]
        : [show];
    }),
  ];
  return (
    <>
    <Aurora mix={auroraMix(energyFlow(data, allDevices))} dark={theme === "dark"} />
    <div className="app-shell">
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <a href={BASE} className="brand">
          <span>
            <House size={24} />
          </span>
          <div>
            CASA SALAVAT<small>HOME CONTROL</small>
          </div>
        </a>
        <span className="nav-caption">SPATIUL TAU</span>
        <nav>
          {[
            ["overview", "Acasa", "Acasa", House],
            ["energy", "Energie", "Energie", Zap],
            ["economics", "Costuri si prognoza", "Costuri", Wallet],
            ["policy", "Politica Energie", "Politica", Gauge],
            ["tesla", "Tesla", "Tesla", Car],
            ["devices", "Dispozitive", "Dispozitive", LayoutGrid],
            ["rules", "Automatizari", "Reguli", Workflow],
            ...(adminMode && haAdmin ? [["audit", "Jurnal", "Jurnal", History]] : []),
          ].map(([key, title, short, Icon]: any) => (
            <button
              key={key}
              title={title}
              aria-label={title}
              aria-current={tab === key ? "page" : undefined}
              className={tab === key ? "active" : ""}
              onClick={() => navigate(key)}
            >
              <Icon size={20} />
              <span className="nav-short" aria-hidden="true">{short}</span>
              <span className="nav-label">{title}</span>
              {tab === key && <span className="nav-mark" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            title="Setari"
            aria-label="Setari"
            aria-current={tab === "settings" ? "page" : undefined}
            className={
              "sidebar-setting " + (tab === "settings" ? "active" : "")
            }
            onClick={() => navigate("settings")}
          >
            <Settings size={20} />
            <span className="nav-short" aria-hidden="true">Setari</span>
            <span className="nav-label">Setari</span>
          </button>
          {!localAccount && <a
            className="ha-link"
            title="Home Assistant (fereastra noua)"
            aria-label="Home Assistant"
            href="/home-assistant/"
            target="_blank"
            rel="noreferrer"
          >
            <span className="ha-symbol">
              <ExternalLink size={18} />
            </span>
            <span className="nav-short" aria-hidden="true">HA</span>
            <span className="nav-label">Home Assistant</span>
            <ArrowUpRight size={15} />
          </a>}
          <div className="account">
            <span className="avatar">
              {data?.user.name?.slice(0, 1) || "S"}
            </span>
            <span>
              <strong>{data?.user.name || "Casa Salavat"}</strong>
              <small>{roleName}</small>
            </span>
            {data ? (
              <button
                className="icon-button"
                title="Deconectare"
                aria-label="Deconectare"
                onClick={async () => {
                  try {
                    await post("logout", {});
                    location.reload();
                  } catch (e: any) {
                    setNotice(e.message);
                  }
                }}
              >
                <LogOut size={17} />
              </button>
            ) : (
              <a
                className="icon-button"
                title="Conectare"
                href={BASE + "auth/login"}
              >
                <LogIn size={17} />
              </a>
            )}
          </div>
        </div>
      </aside>
      {mobile && (
        <button
          className="sidebar-shade"
          aria-label="Inchide meniul"
          onClick={() => setMobile(false)}
        />
      )}
      <main>
        <header className="topbar">
          <div className="page-identity">
            <button
              className="icon-button mobile-menu"
              aria-label="Meniu"
              onClick={() => setMobile(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb">
              Casa Salavat <ChevronRight size={13} />
            </span>
            <strong>{titles[tab]}</strong>
          </div>
          <form className="quick-search" onSubmit={event => { event.preventDefault(); setFilter(quickQuery.trim()); setArea("all"); setDeviceFloor("all"); navigate("devices"); }}>
            <Search size={15}/><input type="search" aria-label="Cautare rapida" placeholder="Cauta un dispozitiv..." value={quickQuery} disabled={!data} onChange={event => setQuickQuery(event.target.value)}/><button type="submit" title="Cauta" aria-label="Cauta" disabled={!data}><ArrowUpRight size={15}/></button>
          </form>
          <div className="top-tools">
            <button className="palette-trigger" title="Comenzi rapide (Ctrl+K)" aria-label="Comenzi rapide" aria-haspopup="dialog" disabled={!data} onClick={() => setPalette(true)}>
              <Command size={15}/><kbd>K</kbd>
            </button>
            <div className="theme-toggle" role="group" aria-label="Aspect">
              <button title="Aspect luminos" aria-label="Aspect luminos" aria-pressed={theme === "light"} onClick={(event) => switchTheme("light", event)}><Sun size={15}/></button>
              <button title="Aspect intunecat" aria-label="Aspect intunecat" aria-pressed={theme === "dark"} onClick={(event) => switchTheme("dark", event)}><Moon size={15}/></button>
            </div>
            <span className={"connection " + (data?.connected ? "live" : "")}>
              <i className="status-dot" />
              {loading
                ? "Conectare..."
                : data?.connected
                  ? "HA Live"
                  : data
                    ? "Offline"
                    : "Neconectat"}
            </span>
            {role === "configure" && (
              <button
                className={
                  "button mode-button " +
                  (mode === "configure" ? "selected" : "")
                }
                aria-pressed={mode === "configure"}
                aria-label={adminMode ? "Revino la modul User" : "Activeaza modul Admin"}
                title={adminMode ? "Revino la modul User" : "Activeaza modul Admin"}
                onClick={() => {
                  setMode(adminMode ? "control" : "configure");
                  if (tab === "audit") go("overview", true);
                }}
              >
                {adminMode ? <ShieldCheck size={16}/> : <UserRound size={16}/>}
                <span>{adminMode ? "Admin" : "User"}</span>
              </button>
            )}
            {data && role !== "configure" && <span className="access-chip"><UserRound size={14}/><span>{localAccount ? roleName : role === "control" ? "User" : "Vizualizare"}</span></span>}
            <button
              className={"pause-button " + (paused ? "paused" : "")}
              title={
                paused
                  ? "Dezactiveaza pauza globala"
                  : "Opreste toate automatizarile"
              }
              aria-label={
                paused
                  ? "Dezactiveaza pauza globala"
                  : "Opreste toate automatizarile"
              }
              disabled={!canControl || (paused && !canConfigure)}
              onClick={() =>
                ask(
                  bindings.pause,
                  paused ? "turn_off" : "turn_on",
                  undefined,
                  paused
                    ? "Dezactivezi pauza globala?"
                    : "Opresti toate automatizarile?",
                )
              }
            >
              {paused ? <CirclePause size={19} /> : <CircleStop size={19} />}
              <span>{paused ? "In pauza" : "Oprire globala"}</span>
            </button>
          </div>
        </header>
        {!data && !loading && (
          <div className="auth-band">
            <LockKeyhole size={18} />
            <span>Conecteaza-te pentru starea si controlul casei.</span>
            {loginButton}
          </div>
        )}
        {data && !data.connected && (
          <div className="offline-band">
            <WifiOff size={18} />
            Conexiunea cu HA este intrerupta. Comenzile sunt blocate.
          </div>
        )}
        {tab === "overview" ? (
          <>
            <HomeDashboard data={data} devices={allDevices} history={history}
              room={area} floor={deviceFloor} onLocation={(floor,room)=>{setDeviceFloor(floor);setArea(room);}}
              canControl={canControl && !pending} control={entityControl}
              temperature={(entity, target) => setDialog({kind: "temperature", entity, value: target, title: name(entity)})}
              brightness={(entity, percent) => send(entity.entity_id, "set_brightness", percent)}
              navigate={navigate} layout={layout} onLayout={changeLayout} onArrange={refreshUsage}/>
            {chart()}
          </>
        ) : tab === "tesla" ? (
          <Tesla data={data} />
        ) : tab === "battery" ? (
          <BatteryPanel data={data} />
        ) : tab === "energy" ? (
          <>
            {stats(true)}
            <div className="energy-workspace">
              <section className="scene-section">
                <div className="scene-heading">
                  <div>
                    <span className="eyebrow">ENERGIE / STOCARE / CONSUM</span>
                    <h1>Fluxuri energetice</h1>
                  </div>
                  <button className="button" onClick={() => navigate('economics')}><Wallet size={16}/>Costuri si prognoza</button>
                </div>
                <div className="energy-instruments">
                  {[
                    ["solar", "solar", "Panouri", Sun, "kW", `${format(value(data, "solarToday"))} kWh astazi`],
                    ["house", "load", "Casa", House, "kW", `${format(value(data, "loadToday"))} kWh astazi`],
                    ["battery", "soc", "Baterie", Battery, "%", (value(data, "charge") || 0) > 0.03 ? `Incarcare ${format(value(data, "charge"), 2)} kW` : (value(data, "discharge") || 0) > 0.03 ? `Descarcare ${format(value(data, "discharge"), 2)} kW` : value(data, "charge") === null && value(data, "discharge") === null ? "Fara citire" : "In repaus"],
                    ["grid", "import", "Import", Cable, "kW", `Export ${format(value(data, "export"), 2)} kW`],
                    ["tesla", "tesla", "Tesla", Car, "kW", "Putere incarcare"],
                  ].map(([id, key, title, Icon, unit, detail]: any) => (
                    <button key={id} className={"energy-instrument " + id + (selected === id ? " selected" : "")} onClick={() => id === "battery" ? navigate("battery") : setSelected(id)} aria-pressed={selected === id}>
                      <span className="instrument-icon"><Icon size={24} /></span>
                      <span className="instrument-name">{title}</span>
                      <strong>{format(value(data, key))}<small> {unit}</small></strong>
                      <small className="instrument-detail">{detail}</small>
                      {id === "battery" && <span className="instrument-meter" aria-hidden="true"><i style={{ width: Math.max(0, Math.min(100, value(data, "soc") || 0)) + "%" }} /></span>}
                    </button>
                  ))}
                </div>
              </section>
              {inspector()}
            </div>
            {chart()}
          </>
        ) : tab === "devices" ? (
          <section className="page-section">
            <div className="section-top">
              <div>
                <span className="eyebrow">{allDevices.filter(d => !d.pending).length} INTEGRATE / {allDevices.filter(d => d.pending && !d.external).length} DE INTEGRAT</span>
                <h1>Dispozitivele casei</h1>
              </div>
              <div className="device-filters">
                <label className="search">
                  <Search size={17} />
                  <input
                    type="search"
                    aria-label="Cauta dispozitive"
                    placeholder="Cauta dispozitive"
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  />
                </label>
                {data && <button className={"button arrange-toggle" + (arrangeInventory ? " selected" : "")} aria-pressed={arrangeInventory} onClick={() => { if (!arrangeInventory) refreshUsage(); setArrangeInventory(!arrangeInventory); }}><ArrowUpDown size={16} />Aranjeaza</button>}
                <select
                  aria-label="Camera"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                >
                  <option value="all">Toate camerele</option>
                  {[...new Set([...houseRooms(data, deviceFloor), ...allDevices.filter(d => deviceFloor === "all" || d.floor === deviceFloor).map((d) => d.area)])]
                    .sort()
                    .map((a) => (
                      <option key={a}>{a}</option>
                    ))}
                </select>
              </div>
            </div>
            {data && <div className="floor-tabs device-floor-tabs" role="tablist" aria-label="Nivel dispozitive">{["all", ...houseFloors(data), ...(allDevices.some(d => d.floor === "Neatribuite") ? ["Neatribuite"] : [])].map(f => <button role="tab" key={f} aria-selected={deviceFloor === f} onClick={() => { setDeviceFloor(f); setArea("all"); }}>{f === "all" ? "Toate nivelurile" : f}</button>)}</div>}
            {!data ? (
              <div className="empty-state">
                <LockKeyhole />
                {loginButton}
              </div>
            ) : shown.length ? (
              <>
              {arrangeInventory && <ArrangeBar sort={layout.sort} days={layout.usage_days || 30} onSort={(sort) => changeLayout({ sort })} onDone={() => setArrangeInventory(false)} />}
              <div className={"device-grid" + (arrangeInventory ? " arranging" : "")}>{arrangeInventory
                ? inventorySorter.preview("inventory", arrange(shown, layout).map((d) => d.id)).map((id) => { const d = shown.find((x) => x.id === id)!; const ids = arrange(shown, layout).map((x) => x.id);
                    return <Sortable key={id} sorter={inventorySorter} scope="inventory" ids={ids} id={id} name={d.name} uses={layout.sort === "usage" ? usesOf(d) : null}>{deviceCard(d)}</Sortable>; })
                : arrange(shown, layout).map(deviceCard)}</div>
              </>
            ) : (
              <div className="empty-state">
                <Search />
                <span>Niciun dispozitiv pentru filtrele alese.</span>
              </div>
            )}
          </section>
        ) : tab === "economics" ? (
          data && <EnergyEconomics snapshot={data} canConfigure={canConfigure} openPolicy={() => navigate('policy')}/>
        ) : tab === "policy" ? (
          data && <EnergyPolicy snapshot={data} canConfigure={canConfigure} canControl={canControl}/>
        ) : tab === "rules" ? (
          rules()
        ) : tab === "audit" && adminMode && haAdmin ? (
          <section className="page-section">
            <div className="section-top">
              <h1>Jurnal de comenzi</h1>
              <ShieldCheck size={21} />
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Utilizator</th>
                    <th>Actiune</th>
                    <th>Entitate</th>
                    <th>Rezultat</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((r, i) => (
                    <tr key={i}>
                      <td>
                        {new Date(r.at * 1000).toLocaleString("ro-RO", {
                          timeZone: "Europe/Bucharest",
                        })}
                      </td>
                      <td>{r.name || "Utilizator"}</td>
                      <td>{r.action}</td>
                      <td>{r.entity}</td>
                      <td>{r.result}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!audit.length && (
                <div className="empty-state">
                  <History />
                  <span>Nu exista comenzi inregistrate in aplicatie.</span>
                </div>
              )}
            </div>
          </section>
        ) : (
          <section className="page-section">
            <div className="section-top">
              <div>
                <span className="eyebrow">POLITICI SI ACCES</span>
                <h1>Setarile casei</h1>
              </div>
              <ShieldCheck size={22} />
            </div>
            {!data ? (
              <div className="empty-state">
                <LockKeyhole />
                {loginButton}
              </div>
            ) : !adminMode ? (
              <section className="account-settings">
                <div className="account-profile"><span className="avatar">{data.user.name.slice(0, 1)}</span><div><h2>{data.user.name}</h2><span className="role-badge">{localAccount ? "Cont Casa / " + roleName.toLowerCase() : role === "configure" ? "Administrator Home Assistant / mod User" : role === "control" ? "User / control dispozitive" : "Doar vizualizare"}</span></div></div>
                <div className="setting-row"><span>Autentificare</span><strong>{localAccount ? "Cont Casa, parola si cod din aplicatie" : "Cont Home Assistant"}</strong></div>
                <div className="setting-row"><span>Sesiune pe acest dispozitiv</span><strong>Ramai conectat 30 de zile de la ultima folosire</strong></div>
                <div className="setting-row"><span>Configurare si automatizari</span><strong>{role === "configure" ? (localAccount ? "Parametri in modul Admin" : "Disponibile in modul Admin") : "Doar administrator"}</strong></div>
                <div className="setting-row"><span>Aspect</span><div className="theme-toggle" role="group" aria-label="Aspect cont"><button title="Luminos" aria-label="Luminos" aria-pressed={theme === "light"} onClick={(event) => switchTheme("light", event)}><Sun size={15}/></button><button title="Intunecat" aria-label="Intunecat" aria-pressed={theme === "dark"} onClick={(event) => switchTheme("dark", event)}><Moon size={15}/></button></div></div>
                <div className="account-actions">
                  {role === "configure" && <button className="button primary" onClick={() => setMode("configure")}><ShieldCheck size={16}/>Deschide administrarea</button>}
                  <button className="button" onClick={() => setDialog({ kind: "sessions", title: "Deconectezi toate dispozitivele?" })}><LogOut size={16}/>Deconecteaza toate dispozitivele</button>
                </div>
                {localAccount && <PasswordChange post={post} notify={setNotice} />}
                {haAdmin && <p className="field-hint">Conturile Casa (fara HA) se administreaza din modul Admin, la Setari.</p>}
              </section>
            ) : (
              <div className="settings-grid">
                <section>
                  <h2>Baterie si prognoza</h2>
                  <div className="priority-line">
                    <House size={15} />
                    Casa
                    <ChevronRight size={12} />
                    <Battery size={15} />
                    Baterie
                    <ChevronRight size={12} />
                    <Car size={15} />
                    Tesla
                  </div>
                  {Object.keys(helpers)
                    .filter((id) => id === 'input_number.deye_battery_min_soc' || id === 'input_number.deye_battery_max_discharge_kw')
                    .map(field)}
                  <div className="setting-row">
                    <span>Management automat baterie</span>
                    <button
                      className="toggle"
                      role="switch"
                      aria-label="Management automat baterie"
                      aria-checked={s("manager")?.state === "on"}
                      disabled={!canConfigure || pending}
                      onClick={() =>
                        ask(
                          bindings.manager,
                          s("manager")?.state === "on" ? "turn_off" : "turn_on",
                          undefined,
                          "Modifici managementul automat al bateriei?",
                        )
                      }
                    />
                  </div>
                  <div className="setting-row">
                    <span>Incarcare din retea</span>
                    <strong>Dezactivata in politica HA</strong>
                  </div>
                </section>
                <section>
                  <h2>Confort si consumatori</h2>
                  {data.states['sensor.home_energy_policy_status'] ? <button className="button" onClick={() => navigate('policy')}><SlidersHorizontal size={16}/>Politica Energie</button> : [["input_boolean.ariston_solar_boost_enabled", "Program automat boiler"], ["input_boolean.hvac_solar_climate_enabled", "Program automat climatizare"]].map(([id, title]) => <div className="setting-row" key={id}><span>{title}</span><button className="toggle" role="switch" aria-label={title} aria-checked={data.states[id]?.state === "on"} disabled={!canConfigure || !valid(data.states[id]) || pending} onClick={() => ask(id, data.states[id]?.state === "on" ? "turn_off" : "turn_on", undefined, `${data.states[id]?.state === "on" ? "Opresti" : "Pornesti"} ${title.toLowerCase()}?`)}/></div>)}
                  {!localAccount && <a className="text-button" href="/home-assistant/config/integrations/integration/tesla_custom" target="_blank" rel="noreferrer">Reautentificare Tesla in HA<ArrowUpRight size={16}/></a>}
                  {Object.keys(helpers)
                    .filter((id) => !id.includes("deye") && !data.states['sensor.home_energy_policy_status'])
                    .map(field)}
                  {haAdmin && (
                    <>
                      <h2 className="users-title">Acces utilizatori</h2>
                      {users.map((user) => (
                        <div className="setting-row" key={user.id}>
                          <span>{user.name}</span>
                          {user.is_admin || user.role === "configure" ? (
                            <span className="role-badge"><ShieldCheck size={14}/>Admin HA</span>
                          ) : (
                            <select
                              aria-label={"Acces " + user.name}
                              value={user.role}
                              disabled={!canConfigure}
                              onChange={async (e) => {
                                const next = e.target.value;
                                try {
                                  await post("users/" + user.id, {
                                    role: next,
                                  });
                                  setUsers(
                                    users.map((u) =>
                                      u.id === user.id
                                        ? { ...u, role: next }
                                        : u,
                                    ),
                                  );
                                  setNotice("Acces actualizat.");
                                } catch (e: any) {
                                  setNotice(e.message);
                                }
                              }}
                            >
                              <option value="viewer">Vizualizare</option>
                              <option value="control">User - control</option>
                            </select>
                          )}
                        </div>
                      ))}
                      <a className="text-button" href="/home-assistant/config/users" target="_blank" rel="noreferrer">Conturi Home Assistant<ArrowUpRight size={16}/></a>
                      <LocalUsers post={post} notify={setNotice} enabled={canConfigure} />
                    </>
                  )}
                </section>
              </div>
            )}
          </section>
        )}
        <footer className="page-footer">
          <span>
            <ShieldCheck size={13} />
            Conexiune locala prin Home Assistant
          </span>
          <span>
            Casa Salavat <span className="footer-dot">/</span> v0.1
          </span>
        </footer>
      </main>
      <nav className="mobile-nav" aria-label="Navigare mobila">
        {[
          ["overview", "Acasa", House],
          ["energy", "Energie", Zap],
          ["policy", "Politica", Gauge],
          ["devices", "Dispozitive", LayoutGrid],
          ["rules", "Automatizari", Workflow],
        ].map(([key, title, Icon]: any) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => navigate(key)}
          >
            {tab === key && <span className="dock-mark" aria-hidden="true" />}
            <Icon size={19} />
            {title}
          </button>
        ))}
      </nav>
      {notice && (
        <div className="toast" role="status">
          {notice}
          <button
            className="icon-button"
            title="Inchide mesajul"
            aria-label="Inchide mesajul"
            onClick={() => setNotice("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {modal()}
      {palette && data && <CommandPalette items={paletteItems()} onClose={() => setPalette(false)} />}
    </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
