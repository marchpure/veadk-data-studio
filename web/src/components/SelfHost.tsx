import { useState } from "react";
import {
  DockerIcon,
  CopyIcon,
  BookIcon,
  GithubIcon,
  LockIcon,
  ShieldIcon,
  ChatIcon,
  CpuIcon,
} from "@/components/landing/icons";
import { trackCtaClick } from "@/lib/analytics";

const GITHUB_URL = "https://github.com/byaan-ai/byaan";
const INSTALL_CMD =
  "curl -fsSL https://downloads.byaan.ai/docker/install.sh | bash";

const installOutput = [
  <span key="1" className="out-line"><span className="dim">[+]</span> Downloading start.sh, .env, README.md</span>,
  <span key="2" className="out-line"><span className="info">→</span> APP_SECRET generated · <span className="dim">edit .env, then ./start.sh</span></span>,
  <span key="3" className="out-line"><span className="ok">✓</span> Byaan running on <span style={{ color: "var(--fg)" }}>http://localhost:8080</span></span>,
  <span key="4" className="out-line"><span className="dim">postgres · backend · caddy · supervisord — one container</span></span>,
];

const included = [
  {
    Icon: () => <LockIcon size={18} />,
    title: "Multi-user auth + RBAC",
    body: "Invite teammates by email, assign roles. Master admin created on first run.",
  },
  {
    Icon: () => <ChatIcon size={18} />,
    title: "Slack integration",
    body: "Add to your workspace. Tag @byaan in any channel — answers in the thread.",
  },
  {
    Icon: () => <CpuIcon size={18} />,
    title: "Google OAuth",
    body: "Drop in client ID and secret to enable SSO. Optional.",
  },
  {
    Icon: () => <ShieldIcon size={18} />,
    title: "Automatic HTTPS",
    body: "Set DOMAIN in .env — Caddy fetches a Let's Encrypt cert. No proxy config.",
  },
  {
    Icon: () => <DockerIcon size={18} />,
    title: "Zero-downtime updates",
    body: "Blue-green deploys on ./start.sh update. Optional auto-update nightly.",
  },
  {
    Icon: () => <BookIcon size={18} />,
    title: "Shared dashboards",
    body: "Notebooks, dashboards, and skills shared across your org.",
  },
];

const SelfHost = () => {
  const [running, setRunning] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyCmd = async () => {
    try {
      await navigator.clipboard.writeText(INSTALL_CMD);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <section className="self-host" id="self-host">
      <div className="container">
        <div className="section-head reveal">
          <span className="section-eyebrow accent">For teams</span>
          <h2 className="section-title">Byaan Team Version</h2>
          <p className="section-sub">
            One-line install. Multi-user auth, RBAC, Slack, and automatic HTTPS — out of the box. Runs in your VPC. AGPL licensed.
          </p>
        </div>

        <div
          className="self-host-grid reveal"
          style={{
            gridTemplateColumns: "1fr",
            maxWidth: 720,
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          <div className={`deploy-card ${running ? "running" : ""}`}>
            <div className="deploy-icon">
              <DockerIcon />
            </div>
            <div className="deploy-title">5-minute install</div>
            <div className="deploy-prereq">
              Linux + Docker · 2 GB RAM (4 GB recommended) · ports 80/443 or 8080 free
            </div>

            <div className="deploy-step">
              <div className="deploy-step-num">1</div>
              <div className="deploy-step-content">
                <div className="deploy-step-title">Install</div>
                <span className="run-hint">{running ? "running" : "click to run"}</span>
                <div
                  className="deploy-code"
                  onClick={(ev) => {
                    if ((ev.target as HTMLElement).closest(".deploy-copy")) return;
                    setRunning((r) => !r);
                  }}
                  style={{ fontSize: 11.5, wordBreak: "break-all", whiteSpace: "normal", lineHeight: 1.55, paddingRight: 40 }}
                >
                  <span>{INSTALL_CMD}</span>
                  <span
                    className="deploy-copy"
                    title="Copy"
                    style={copied ? { color: "var(--green)" } : undefined}
                    onClick={(ev) => {
                      ev.preventDefault();
                      ev.stopPropagation();
                      copyCmd();
                    }}
                  >
                    {copied ? (
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : (
                      <CopyIcon size={11} />
                    )}
                  </span>
                </div>
                <div className="deploy-step-hint">
                  Drops <code className="inline-code">start.sh</code> and <code className="inline-code">.env</code> into <code className="inline-code">./byaan</code>. <code className="inline-code">APP_SECRET</code> is auto-generated.
                </div>
              </div>
            </div>

            <div className="deploy-step">
              <div className="deploy-step-num">2</div>
              <div className="deploy-step-content">
                <div className="deploy-step-title">Configure</div>
                <div className="deploy-step-hint">
                  Open <code className="inline-code">.env</code> and set:
                  <ul className="deploy-step-list">
                    <li><code className="inline-code">MASTER_USER_EMAIL</code> — admin email</li>
                    <li><code className="inline-code">MASTER_USER_PASSWORD</code> — 8+ characters</li>
                    <li><code className="inline-code">ORG_NAME</code> — your organization</li>
                    <li><code className="inline-code">DOMAIN</code> <span className="dim">(optional — enables Let's Encrypt HTTPS)</span></li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="deploy-step">
              <div className="deploy-step-num">3</div>
              <div className="deploy-step-content">
                <div className="deploy-step-title">Start</div>
                <div className="deploy-code" style={{ fontSize: 11.5, lineHeight: 1.55 }}>
                  ./start.sh
                </div>
                <div className="deploy-step-hint">
                  Live on <code className="inline-code">:8080</code> (or your <code className="inline-code">DOMAIN</code>). Sign in as the master admin you configured, then invite teammates from the admin panel.
                </div>
              </div>
            </div>

            <div className="deploy-output">{installOutput}</div>
          </div>
        </div>

        <div
          className="reveal"
          style={{ marginTop: 56, maxWidth: 720, marginLeft: "auto", marginRight: "auto" }}
        >
          <div className="deploy-card">
            <div className="deploy-title" style={{ marginBottom: 4 }}>Update &amp; logs</div>
            <div className="deploy-prereq" style={{ marginBottom: 20 }}>
              Keep your instance current and monitor services with these commands.
            </div>

            <div className="deploy-step">
              <div className="deploy-step-num">↑</div>
              <div className="deploy-step-content">
                <div className="deploy-step-title">Update</div>
                <div className="deploy-code" style={{ fontSize: 11.5, lineHeight: 1.55 }}>
                  ./start.sh update
                </div>
                <div className="deploy-step-hint">
                  Run this command to deploy the latest version.
                </div>
              </div>
            </div>

            <div className="deploy-step">
              <div className="deploy-step-num">≡</div>
              <div className="deploy-step-content">
                <div className="deploy-step-title">Logs</div>
                <div className="deploy-code" style={{ fontSize: 11.5, lineHeight: 1.55 }}>
                  ./start.sh logs
                </div>
                <div className="deploy-step-hint">
                  Tail all services. Scope to one service by passing its name:
                  <ul className="deploy-step-list">
                    <li><code className="inline-code">./start.sh logs backend</code> — FastAPI</li>
                    <li><code className="inline-code">./start.sh logs caddy</code> — reverse proxy</li>
                    <li><code className="inline-code">./start.sh logs postgres</code> — database</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="deploy-step" style={{ borderBottom: "none", paddingBottom: 0 }}>
              <div className="deploy-step-num">●</div>
              <div className="deploy-step-content">
                <div className="deploy-step-title">Status</div>
                <div className="deploy-code" style={{ fontSize: 11.5, lineHeight: 1.55 }}>
                  ./start.sh status
                </div>
                <div className="deploy-step-hint">
                  Check whether Byaan is running.
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          className="reveal"
          style={{
            marginTop: 56,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 12,
          }}
        >
          {included.map((item) => (
            <div key={item.title} className="feature-card">
              <div className="feature-icon">
                <item.Icon />
              </div>
              <div className="feature-title">{item.title}</div>
              <div className="feature-body">{item.body}</div>
            </div>
          ))}
        </div>

        <div className="self-host-cta reveal" style={{ marginTop: 48 }}>
          <a
            className="btn btn-primary btn-lg"
            href="/docs"
            onClick={() => trackCtaClick({ cta: "selfhost_docs", location: "self_host", url: "/docs" })}
          >
            <BookIcon size={16} />
            Read the team version docs
          </a>
          <a
            className="btn btn-outline btn-lg"
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackCtaClick({ cta: "star_github", location: "self_host", url: GITHUB_URL })}
          >
            <GithubIcon size={16} />
            Star on GitHub
          </a>
        </div>
        <div className="self-host-foot">
          AGPL licensed · Your VPC, your keys · Optional Let's Encrypt HTTPS · Blue-green updates
        </div>
      </div>
    </section>
  );
};

export default SelfHost;
