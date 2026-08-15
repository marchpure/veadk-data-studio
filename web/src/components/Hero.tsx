import { useEffect, useRef, useState } from "react";
import { useDownload } from "@/hooks/useDownload";
import { trackCtaClick, trackDownloadClick } from "@/lib/analytics";
import {
  GithubIcon,
  DownloadIcon,
  SlackIcon,
  MacIcon,
  TerminalIcon,
  BotIcon,
  CamSlackIcon,
  ClaudeIcon,
  CursorIcon,
  McpIcon,
} from "@/components/landing/icons";

const GITHUB_URL = "https://github.com/byaan-ai/byaan";
const CYCLE_MS = 6000;
const CYCLE_START_DELAY = 5200;
const PANES = ["slack", "mac", "cc"] as const;
type Pane = typeof PANES[number];

const Hero = () => {
  const { isMac, architecture, appleUrl, intelUrl } = useDownload();
  const canShowDownload = isMac && architecture !== "unknown";
  const downloadUrl = architecture === "apple-silicon" ? appleUrl : intelUrl;

  const [activePane, setActivePane] = useState<Pane>("slack");
  const [cycleStopped, setCycleStopped] = useState(false);
  const cycleStartRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const tabRefs = useRef<Record<Pane, HTMLSpanElement | null>>({ slack: null, mac: null, cc: null });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      cycleStartRef.current = performance.now();
      const tick = () => {
        if (cycleStopped) return;
        const elapsed = performance.now() - cycleStartRef.current;
        const pct = Math.min(100, (elapsed / CYCLE_MS) * 100);
        const activeEl = document.querySelector<HTMLElement>(".byaan-landing .demo-tab.active");
        if (activeEl) activeEl.style.setProperty("--cycle-progress", pct + "%");
        if (pct >= 100) {
          setActivePane((curr) => {
            const idx = PANES.indexOf(curr);
            return PANES[(idx + 1) % PANES.length];
          });
          cycleStartRef.current = performance.now();
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    }, CYCLE_START_DELAY);

    return () => {
      window.clearTimeout(timeout);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [cycleStopped]);

  const stopCycle = () => {
    setCycleStopped(true);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    document.querySelectorAll<HTMLElement>(".byaan-landing .demo-tab").forEach((t) => {
      t.classList.remove("cycling");
      t.style.removeProperty("--cycle-progress");
    });
  };

  const handleTabClick = (pane: Pane) => {
    stopCycle();
    setActivePane(pane);
  };

  const isCycling = !cycleStopped;
  const tabClass = (pane: Pane) =>
    `demo-tab ${activePane === pane ? "active" : ""} ${activePane === pane && isCycling ? "cycling" : ""}`;
  const paneClass = (pane: Pane) => `demo-pane ${activePane === pane ? "active" : ""}`;

  return (
    <section className="hero">
      <div className="container">
        <div className="hero-pills">
          <span className="pill"><span className="pill-dot"></span>Slack-native</span>
          <span className="pill">Available via MCP</span>
          <span className="pill">Read-only by design</span>
        </div>

        <h1>
          The AI data analyst<br />
          <span className="grad">your team actually owns.</span>
        </h1>

        <p className="hero-sub">
          Ask in Slack, on Mac, or via MCP. Byaan learns your business once — your whole team runs it as skills. Read-only by design.
        </p>

        <div className="hero-cta">
          <a
            className="btn btn-primary btn-lg"
            href={canShowDownload ? downloadUrl : "#download"}
            onClick={() =>
              trackDownloadClick({
                location: "hero",
                arch: architecture,
                url: canShowDownload ? downloadUrl : "#download",
                is_mac: isMac,
              })
            }
          >
            <DownloadIcon size={16} />
            Download for Mac
          </a>
          <a
            className="btn btn-outline btn-lg"
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackCtaClick({ cta: "star_github", location: "hero", url: GITHUB_URL })}
          >
            <GithubIcon size={16} />
            Star on GitHub
          </a>
          <a
            className="btn btn-ghost btn-lg"
            href="/docs"
            onClick={() => trackCtaClick({ cta: "docs", location: "hero", url: "/docs" })}
          >
            Read the docs →
          </a>
        </div>

        <p className="hero-microcopy">Free Mac app · MIT licensed · Self-host the team version · AGPL</p>

        {/* Hero demo */}
        <div className="hero-demo">
          <div className="demo-card">
            <div className="demo-chrome">
              <div className="traffic"><span></span><span></span><span></span></div>
              <div className="demo-chrome-tabs">
                <span
                  ref={(el) => (tabRefs.current.slack = el)}
                  className={tabClass("slack")}
                  data-pane="slack"
                  onClick={() => handleTabClick("slack")}
                >
                  <SlackIcon className="demo-tab-icon" />
                  #analytics · slack
                </span>
                <span
                  ref={(el) => (tabRefs.current.mac = el)}
                  className={tabClass("mac")}
                  data-pane="mac"
                  onClick={() => handleTabClick("mac")}
                >
                  <MacIcon className="demo-tab-icon" />
                  Mac app
                </span>
                <span
                  ref={(el) => (tabRefs.current.cc = el)}
                  className={tabClass("cc")}
                  data-pane="cc"
                  onClick={() => handleTabClick("cc")}
                >
                  <TerminalIcon className="demo-tab-icon" />
                  Claude Code
                </span>
              </div>
            </div>

            <div className="demo-body">
              {/* SLACK PANE */}
              <div className={paneClass("slack")} data-pane="slack" key={`slack-${activePane}`}>
                <div className="slack-msg">
                  <div className="slack-avatar user">U</div>
                  <div style={{ flex: 1 }}>
                    <div className="slack-meta">
                      <span className="slack-name">User</span>
                      <span className="slack-time">10:42 AM</span>
                    </div>
                    <div className="slack-content">
                      <span className="typing-line">
                        <span className="mention">@byaan</span> monthly revenue by product line for Q4, save as <code>q4-revenue-deck</code>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="thinking">
                  <span className="thinking-dots"><span></span><span></span><span></span></span>
                  Loading skills · checking <span style={{ color: "var(--fg-2)" }}>fct_revenue</span> · fiscal year starts Feb 1
                </div>

                <div className="ai-response">
                  <div className="slack-msg">
                    <div className="slack-avatar bot">
                      <BotIcon />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div className="slack-meta">
                        <span className="slack-name">Byaan</span>
                        <span style={{ fontFamily: "var(--mono)", fontSize: 10, padding: "1px 6px", background: "var(--primary-soft)", color: "var(--primary)", borderRadius: 3, border: "1px solid var(--primary-line)" }}>APP</span>
                        <span className="slack-time">10:42 AM</span>
                      </div>
                      <div className="answer-text">
                        Q4 revenue reached <span className="num">$2.4M</span> across 3 product lines.{" "}
                        <span className="num">Enterprise</span> led with <span className="num">48%</span> share, up{" "}
                        <span className="up">+18.7% YoY</span>. Saved as skill{" "}
                        <span className="skill">@byaan q4-revenue-deck</span>
                      </div>

                      <div className="mini-dash">
                        <div className="mini-dash-head">
                          <div className="mini-dash-title">
                            Q4 revenue · by product line
                            <span className="skill-tag">
                              <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="6" /></svg>
                              skill saved
                            </span>
                          </div>
                          <div className="mini-dash-actions">
                            <span>↗ Open</span>
                            <span>⤓ PDF</span>
                            <span>⎘ Excel</span>
                          </div>
                        </div>
                        <div className="mini-dash-grid">
                          <div className="metric"><div className="metric-label">Total Revenue</div><div className="metric-value">$2.4M</div><div className="metric-delta">↑ 12.3%</div></div>
                          <div className="metric"><div className="metric-label">Top Product</div><div className="metric-value">Enterprise</div><div className="metric-delta">↑ 18.7%</div></div>
                          <div className="metric"><div className="metric-label">Growth Rate</div><div className="metric-value">23.4%</div><div className="metric-delta">↑ 5.1%</div></div>
                        </div>
                        <div className="chart">
                          {[35, 45, 28, 55, 42, 65, 50, 72, 58, 80, 68, 92].map((h, i) => (
                            <div
                              key={i}
                              className={`chart-bar ${i >= 9 ? "hot" : ""}`}
                              style={{ height: `${h}%`, animationDelay: `${5.1 + i * 0.06}s` }}
                            />
                          ))}
                        </div>
                        <div className="chart-axis">
                          <span>Jan</span><span>Apr</span><span>Jul</span><span>Oct</span><span>Dec</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* MAC PANE */}
              <div className={paneClass("mac")} data-pane="mac">
                <div className="mac-app">
                  <div className="mac-chat">
                    <div className="mac-pane-head" style={{ paddingBottom: 10, marginBottom: 14 }}>
                      <span style={{ color: "var(--fg-2)" }}>Q4 Revenue Analysis</span>
                      <span style={{ color: "var(--green)", fontSize: 11 }}>● claude-opus-4.5</span>
                    </div>
                    <div className="mac-user-msg">
                      Build me the Q4 revenue deck — same structure as last quarter, with cohort retention as the closer.
                    </div>
                    <div className="mac-asst-msg">I'll run this through your saved skills first to keep the structure consistent.</div>
                    <div className="mac-tool">
                      <div className="mac-tool-icon" style={{ background: "hsla(24,95%,53%,0.15)", color: "var(--primary)" }}>☰</div>
                      <div className="mac-tool-body">
                        <div className="mac-tool-title">Loading skill <span className="mac-tool-skill">q4-revenue-deck</span></div>
                        <div className="mac-tool-meta">team · used 12 times</div>
                      </div>
                      <div className="mac-tool-status">✓</div>
                    </div>
                    <div className="mac-tool">
                      <div className="mac-tool-icon" style={{ background: "hsla(330,81%,60%,0.15)", color: "var(--accent)" }}>☰</div>
                      <div className="mac-tool-body">
                        <div className="mac-tool-title">Loading skill <span className="mac-tool-skill">cohort-retention</span></div>
                        <div className="mac-tool-meta">org · monthly cohorts by signup channel</div>
                      </div>
                      <div className="mac-tool-status">✓</div>
                    </div>
                    <div className="mac-tool">
                      <div className="mac-tool-icon" style={{ background: "var(--bg-4)", color: "var(--fg-3)" }}>⧉</div>
                      <div className="mac-tool-body">
                        <div className="mac-tool-title">query · fct_revenue</div>
                        <div className="mac-tool-meta"><span style={{ color: "var(--blue)" }}>postgres</span> · prod-replica · read-only</div>
                      </div>
                      <div className="mac-tool-status">✓</div>
                    </div>
                    <div className="mac-asst-msg" style={{ color: "var(--fg-2)" }}>
                      Q4 came in at <b style={{ color: "var(--fg)" }}>$2.4M</b>, up <b style={{ color: "var(--fg)" }}>+12.3%</b>. Building the artifact now →
                    </div>
                    <div className="mac-input-bar">
                      <span className="mac-input-placeholder">Type your message…</span>
                      <div className="mac-input-chips">
                        <span className="mac-chip"><span style={{ color: "var(--primary)" }}>◉</span> postgres</span>
                        <span className="mac-chip">⧉ Data</span>
                        <span className="mac-chip">☰ Plan</span>
                      </div>
                    </div>
                  </div>
                  <div className="mac-preview">
                    <div className="mac-preview-head">
                      <div className="mac-preview-tabs">
                        <span className="mac-preview-tab active">▷ Preview</span>
                        <span className="mac-preview-tab">&lt;/&gt; Code</span>
                      </div>
                      <div className="mac-preview-actions">
                        <span>PDF</span><span>Share</span><span>⛶</span>
                      </div>
                    </div>
                    <div className="mac-preview-body">
                      <div className="mac-art-title">Q4 Revenue Analysis</div>
                      <div className="mac-art-sub">Quarterly revenue with product-line breakdown</div>
                      <div className="mac-art-stats">
                        <div className="mac-art-stat">
                          <div className="mac-art-stat-label">Total</div>
                          <div className="mac-art-stat-num" style={{ background: "linear-gradient(135deg,hsl(248,75%,72%),hsl(265,75%,72%))", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>$2.4M</div>
                        </div>
                        <div className="mac-art-stat">
                          <div className="mac-art-stat-label">Enterprise</div>
                          <div className="mac-art-stat-num" style={{ color: "hsl(38,90%,60%)" }}>48%</div>
                        </div>
                        <div className="mac-art-stat">
                          <div className="mac-art-stat-label">YoY growth</div>
                          <div className="mac-art-stat-num" style={{ background: "linear-gradient(135deg,hsl(248,75%,72%),hsl(265,75%,72%))", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>+18.7%</div>
                        </div>
                      </div>
                      <svg className="mac-art-chart" viewBox="0 0 300 120" preserveAspectRatio="none">
                        <defs>
                          <linearGradient id="macLineFill" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stopColor="hsl(248,75%,72%)" stopOpacity="0.22" />
                            <stop offset="100%" stopColor="hsl(248,75%,72%)" stopOpacity="0" />
                          </linearGradient>
                        </defs>
                        <g stroke="hsl(0,0%,12%)" strokeWidth="1">
                          <line x1="0" y1="30" x2="300" y2="30" />
                          <line x1="0" y1="60" x2="300" y2="60" />
                          <line x1="0" y1="90" x2="300" y2="90" />
                        </g>
                        <path d="M5 60 L40 50 L75 38 L110 30 L145 32 L180 40 L215 28 L250 22 L285 70" fill="none" stroke="hsl(248,75%,72%)" strokeWidth="1.8" />
                        <path d="M5 60 L40 50 L75 38 L110 30 L145 32 L180 40 L215 28 L250 22 L285 70 L285 120 L5 120 Z" fill="url(#macLineFill)" />
                        <path d="M5 65 L40 56 L75 45 L110 38 L145 40 L180 47 L215 35 L250 30 L285 75" fill="none" stroke="hsl(248,75%,72%)" strokeWidth="1.4" strokeOpacity="0.55" strokeDasharray="3,2" />
                        <path d="M5 100 L40 98 L75 96 L110 94 L145 96 L180 95 L215 94 L250 92 L285 106" fill="none" stroke="hsl(38,90%,60%)" strokeWidth="1.6" />
                        <g fill="hsl(248,75%,72%)">
                          <circle cx="40" cy="50" r="1.6" /><circle cx="75" cy="38" r="1.6" /><circle cx="110" cy="30" r="1.6" /><circle cx="145" cy="32" r="1.6" /><circle cx="180" cy="40" r="1.6" /><circle cx="215" cy="28" r="1.6" /><circle cx="250" cy="22" r="1.6" />
                        </g>
                      </svg>
                      <div className="mac-art-axis">
                        <span>W-16</span><span>W-12</span><span>W-8</span><span>W-4</span><span>W-0</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* CLAUDE CODE PANE */}
              <div className={paneClass("cc")} data-pane="cc">
                <div className="cc-line"><span className="prompt">➜</span> ~/eng-repo  <span style={{ color: "var(--accent)" }}>claude</span></div>
                <div className="cc-line" style={{ color: "var(--fg)" }}>why is API p99 latency up this week?</div>
                <div className="cc-tool">
                  <div className="cc-tool-head">byaan.query</div>
                  <div className="cc-tool-body">
                    <div>connecting to <span style={{ color: "var(--fg-2)" }}>prod-metrics</span> · read-only<span style={{ color: "var(--green)" }}> ✓</span></div>
                    <div>using skill <span style={{ color: "var(--accent)" }}>latency-investigation</span> · 24 queries</div>
                    <div><span className="ok">✓</span> p99 up <span style={{ color: "hsl(0,70%,60%)" }}>+38%</span> on <span style={{ color: "var(--fg-2)" }}>/api/v2/search</span></div>
                    <div><span className="ok">✓</span> correlated with deploy <span style={{ color: "var(--fg-2)" }}>a3f9c12</span> · Mon 14:22</div>
                  </div>
                </div>
                <div className="cc-line" style={{ color: "var(--fg-2)", paddingLeft: 2 }}>
                  p99 latency on <span style={{ color: "var(--fg)" }}>/api/v2/search</span> is up{" "}
                  <span style={{ color: "hsl(0,70%,60%)" }}>+38%</span> since deploy{" "}
                  <span style={{ color: "var(--accent)", fontFamily: "var(--mono)" }}>a3f9c12</span> on Mon.{" "}
                  <span style={{ color: "var(--fg-3)" }}>Saved as skill</span>{" "}
                  <span style={{ background: "var(--accent-soft)", color: "var(--accent)", padding: "1px 6px", borderRadius: 4 }}>latency-deploy-correlate</span>
                  <span className="mac-cursor" style={{ width: 6, height: 12 }}></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Client badges */}
        <div style={{ marginTop: 64 }}>
          <div className="hero-badges-label">Works wherever your team works</div>
          <div className="hero-badges">
            <span className="client-badge"><SlackIcon /> Slack</span>
            <span className="client-badge"><CamSlackIcon className="client-logo" /> Mac App</span>
            <span className="client-badge"><ClaudeIcon className="client-logo" /> Claude Code</span>
            <span className="client-badge"><CursorIcon className="client-logo" /> Cursor</span>
            <span className="client-badge"><TerminalIcon className="client-logo" /> Codex</span>
            <span className="client-badge"><McpIcon className="client-logo" /> MCP-compatible</span>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;
