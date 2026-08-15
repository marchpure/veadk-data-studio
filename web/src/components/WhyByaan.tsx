import { useEffect, useRef } from "react";
import { BrainIcon, LockIcon, CpuIcon } from "@/components/landing/icons";

const WhyByaan = () => {
  const yamlRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = yamlRef.current;
    if (!el) return;
    const lines = el.querySelectorAll<HTMLElement>(".yaml-line");
    const newSkill = el.querySelector<HTMLElement>(".yaml-new");

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            lines.forEach((ln, i) => {
              window.setTimeout(() => {
                ln.style.transitionDelay = "0s";
                ln.style.opacity = "1";
                ln.style.transform = "translateX(0)";
              }, i * 110);
            });
            el.classList.add("play");
            if (newSkill) {
              const totalDelay = lines.length * 110 + 800;
              window.setTimeout(() => {
                newSkill.style.display = "";
                newSkill.style.opacity = "1";
                newSkill.style.transform = "translateX(0)";
                newSkill.classList.add("added", "flash");
              }, totalDelay);
            }
            io.unobserve(el);
          }
        }
      },
      { threshold: 0.3 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section className="why">
      <div className="container">
        <div className="section-head reveal">
          <h2 className="section-title">
            Data agents fail because<br />
            they <span style={{ color: "var(--fg-3)" }}>lack context</span>
          </h2>
          <p className="section-sub">
            Generic AI doesn't know your schema, your definitions, or your edge cases. Every session starts from zero.
          </p>
        </div>

        <div className="why-problems">
          <div className="problem-card reveal">
            <div className="problem-quote">"What does <em>revenue</em> mean here?"</div>
            <div className="problem-body">
              Every company defines metrics differently. Generic AI doesn't know your fiscal calendar, your refund policy, or which subscriptions count.
            </div>
          </div>
          <div className="problem-card reveal">
            <div className="problem-quote">"Which table is the source of truth?"</div>
            <div className="problem-body">
              Your data lives across dozens of tables and a few materialized views that lie. AI picks the wrong one more often than not.
            </div>
          </div>
          <div className="problem-card reveal">
            <div className="problem-quote">"Can I trust this answer?"</div>
            <div className="problem-body">
              A confident wrong answer is worse than no answer. Most AI data tools start from zero every session — no memory, no audit trail.
            </div>
          </div>
        </div>

        <div className="section-head reveal" style={{ marginBottom: 80 }}>
          <span className="section-eyebrow accent">The fix</span>
          <h2 className="section-title">Byaan solves this<br />by giving you control</h2>
        </div>

        <div className="solutions">
          {/* Solution 1: Memory + skills */}
          <div className="solution-row reveal">
            <div className="solution-content">
              <div className="icon-tile">
                <BrainIcon />
              </div>
              <h3>Accurate memory across your organization</h3>
              <p>
                Byaan learns your schema, metric definitions, and edge cases once — then saves them as skills the whole org runs correctly every time. New hires inherit the memory your senior analyst spent six months building. Connect GitHub and Byaan reads your codebase to understand the intent behind your data.
              </p>
              <ul className="solution-bullets">
                <li>Learns once, consumed correctly by everyone</li>
                <li>Connect GitHub — Byaan reads code to understand intent</li>
                <li>Same skills work in Slack, Mac, and MCP clients</li>
              </ul>
            </div>
            <div className="visual">
              <div className="visual-head">
                <span className="filename">skills.yaml</span>
                <span style={{ color: "var(--green)" }}>● synced</span>
              </div>
              <div ref={yamlRef} className="yaml yaml-anim">
                <span className="yaml-line"><span className="comment"># context Byaan learned about your team</span></span>
                <span className="yaml-line"><span className="key">context</span>:</span>
                <span className="yaml-line yaml-indent"><span className="nested">revenue</span>: <span className="str">"SUM(line_items.amount) WHERE status='paid'"</span></span>
                <span className="yaml-line yaml-indent"><span className="nested">fiscal_year</span>: <span className="str">"starts February 1"</span></span>
                <span className="yaml-line yaml-indent"><span className="nested">truth_table</span>: <span className="str">"fct_revenue (not mv_revenue_monthly)"</span></span>
                <span className="yaml-line yaml-indent"><span className="nested">refunds</span>: <span className="str">"deducted in same month as charge"</span></span>
                <span className="yaml-line" style={{ marginTop: 14 }}><span className="comment"># named skills your whole team can run</span></span>
                <span className="yaml-line"><span className="key">skills</span>:</span>
                <span className="yaml-line yaml-indent"><span className="nested">q4-revenue-deck</span>: <span className="str">"quarterly revenue + cohorts → PDF"</span></span>
                <span className="yaml-line yaml-indent"><span className="nested">churn-watchlist</span>: <span className="str">"alert when weekly churn &gt; 4%"</span></span>
                <span className="yaml-line yaml-indent"><span className="nested">cohort-retention</span>: <span className="str">"monthly cohorts by signup channel"</span></span>
                <span className="yaml-line yaml-indent yaml-new" style={{ display: "none" }}>
                  <span className="nested">latency-deploy-correlate</span>: <span className="str">"correlate p99 spikes with recent deploys"<span className="yaml-cursor"></span></span>
                </span>
              </div>
            </div>
          </div>

          {/* Solution 2: Own the data */}
          <div className="solution-row reverse reveal">
            <div className="solution-content">
              <div className="icon-tile">
                <LockIcon size={24} />
              </div>
              <h3>You own the data, end to end</h3>
              <p>
                The Mac app runs locally — no signup, no cloud. The team version self-hosts in your infrastructure. Credentials, queries, and results never leave where you put them. Read-only by design means Byaan can't break production.
              </p>
              <ul className="solution-bullets">
                <li>Mac app — free, MIT licensed</li>
                <li>Team version — self-hosted, AGPL licensed</li>
                <li>Your credentials never leave your network</li>
              </ul>
            </div>
            <div className="visual">
              <div className="visual-head">
                <span className="filename">data flow · where things live</span>
              </div>
              <div className="ownership-list">
                <div className="ownership-item featured">
                  <div className="ownership-icon mac">M</div>
                  <div className="ownership-text">
                    <div className="ownership-text-main">Mac App</div>
                    <div className="ownership-text-sub">Runs locally · zero telemetry · MIT licensed</div>
                  </div>
                  <span className="ownership-tag free">free</span>
                </div>
                <div className="ownership-item">
                  <div className="ownership-icon team">T</div>
                  <div className="ownership-text">
                    <div className="ownership-text-main">Team Version</div>
                    <div className="ownership-text-sub">One-line install · auth · Slack · HTTPS</div>
                  </div>
                  <span className="ownership-tag host">team</span>
                </div>
                <div className="ownership-item">
                  <div className="ownership-icon ro">RO</div>
                  <div className="ownership-text">
                    <div className="ownership-text-main">Read-only by design</div>
                    <div className="ownership-text-sub">No DDL · No DML · Safe on production</div>
                  </div>
                  <span className="ownership-tag safe">safe</span>
                </div>
              </div>
              <div className="egress-stage">
                <div className="egress-row">
                  <span className="lhs">network egress · last 24h</span>
                  <span className="live">0 bytes</span>
                </div>
                <div className="egress-track">
                  <span className="egress-laptop">💻 your laptop</span>
                  <span className="egress-packet"></span>
                  <span className="egress-wall">✓ your network</span>
                </div>
                <div className="egress-row" style={{ marginTop: 14 }}>
                  <span className="lhs">queries leaving your network</span>
                  <span style={{ color: "var(--fg)", fontWeight: 600 }}>0</span>
                </div>
              </div>
            </div>
          </div>

          {/* Solution 3: BYOM */}
          <div className="solution-row reveal">
            <div className="solution-content">
              <div className="icon-tile">
                <CpuIcon size={24} />
              </div>
              <h3>Bring your own AI model</h3>
              <p>
                Use your company's federated AI — Azure, Bedrock, Anthropic, OpenAI, Groq, OpenRouter, xAI. Your keys, your billing. Switch any time without losing your skills or context.
              </p>
              <ul className="solution-bullets">
                <li>Works with any OpenAI-compatible API</li>
                <li>No external calls outside the provider you pick</li>
                <li>Switch providers without losing your skills or context</li>
              </ul>
            </div>
            <div className="visual">
              <div className="visual-head">
                <span className="filename">~/.byaan/providers.env</span>
                <span style={{ color: "var(--primary)" }}>BYOM</span>
              </div>
              <div className="providers">
                {[
                  { mark: "A", color: "hsl(28,90%,60%)", name: "Anthropic", note: "Claude — direct API", tag: "active" },
                  { mark: "Az", color: "var(--blue)", name: "Azure OpenAI", note: "your tenant · your billing", tag: "configured" },
                  { mark: "B", color: "hsl(35,80%,60%)", name: "AWS Bedrock", note: "in-VPC inference", tag: "configured" },
                  { mark: "O", color: "hsl(150,55%,55%)", name: "OpenAI · Groq · xAI", note: "any OpenAI-compatible endpoint", tag: "supported" },
                ].map((p) => (
                  <div key={p.name} className="provider">
                    <div className="provider-info">
                      <div className="provider-mark" style={{ color: p.color }}>{p.mark}</div>
                      <div>
                        <div className="provider-name">{p.name}</div>
                        <div className="provider-note">{p.note}</div>
                      </div>
                    </div>
                    <span className="byom-tag">{p.tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default WhyByaan;
