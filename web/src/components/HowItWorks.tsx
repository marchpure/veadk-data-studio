import { useEffect, useRef } from "react";

const steps = [
  {
    num: "01",
    title: "Ask anywhere",
    body: (
      <>
        Slack, the Mac app, or any MCP client — Claude Code, Cursor, Codex. Same Byaan, same context.
      </>
    ),
    meta: "Slack · Mac · MCP",
  },
  {
    num: "02",
    title: "Byaan learns the right answer once",
    body: (
      <>
        Your schema, metric definitions, fiscal calendar, edge cases — saved to organizational memory. Connect GitHub and Byaan reads your codebase to understand intent.
      </>
    ),
    meta: "Persistent · GitHub-aware",
  },
  {
    num: "03",
    title: "The whole team consumes it correctly",
    body: (
      <>
        Turn complex workflows into one-line commands: <code>@byaan cohort-retention</code>. Same logic, same definitions, every time. Versioned, named, shared.
      </>
    ),
    meta: "Versioned · shared",
  },
  {
    num: "04",
    title: "Build dashboards and reports",
    body: (
      <>
        Interactive dashboards, PDF reports, Excel exports, standalone HTML. No backend needed to view.
      </>
    ),
    meta: "PDF · Excel · HTML",
  },
  {
    num: "05",
    title: "Run it your way",
    body: (
      <>
        Free Mac app for individuals. One-line install for teams — auth, Slack, and HTTPS included.
      </>
    ),
    meta: "Mac · One-line install",
  },
];

const HowItWorks = () => {
  const stepsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const stepsEl = stepsRef.current;
    if (!stepsEl) return;
    const stepEls = stepsEl.querySelectorAll<HTMLElement>(".step");

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("in-view");
            const inView = stepsEl.querySelectorAll(".step.in-view").length;
            const pct = (inView / stepEls.length) * 100;
            stepsEl.style.setProperty("--progress", pct + "%");
          }
        }
      },
      { threshold: 0.4, rootMargin: "0px 0px -20% 0px" }
    );
    stepEls.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <section className="how" id="how-it-works">
      <div className="container">
        <div className="section-head reveal">
          <span className="section-eyebrow">Workflow</span>
          <h2 className="section-title">How teams use Byaan</h2>
          <p className="section-sub">
            Five steps from question to shareable answer. Same context wherever your team works.
          </p>
        </div>

        <div className="steps" ref={stepsRef}>
          {steps.map((step) => (
            <div key={step.num} className="step reveal">
              <div className="step-num">{step.num}</div>
              <div className="step-content">
                <div className="step-title">{step.title}</div>
                <div className="step-body">{step.body}</div>
              </div>
              <div className="step-meta">{step.meta}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
