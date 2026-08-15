import { LockIcon, CpuIcon, ShieldIcon } from "@/components/landing/icons";

const TrustStrip = () => {
  return (
    <section className="trust">
      <div className="container">
        <div className="trust-grid">
          <div className="trust-item reveal">
            <div className="icon-tile">
              <LockIcon />
            </div>
            <div className="trust-item-eyebrow">You own the data</div>
            <div className="trust-item-title">Local on your Mac. Self-hosted for your team.</div>
            <p className="trust-item-body">
              Credentials, queries, and results stay where you put them. No cloud hop. No signup. No telemetry.
            </p>
          </div>
          <div className="trust-item reveal">
            <div className="icon-tile">
              <CpuIcon />
            </div>
            <div className="trust-item-eyebrow">Bring your own AI</div>
            <div className="trust-item-title">Claude, OpenAI, Azure, Bedrock — your keys.</div>
            <p className="trust-item-body">
              Use your company's federated AI infrastructure. Switch providers any time. No vendor lock-in.
            </p>
          </div>
          <div className="trust-item reveal">
            <div className="icon-tile">
              <ShieldIcon />
            </div>
            <div className="trust-item-eyebrow">Read-only by design</div>
            <div className="trust-item-title">Never executes DDL or DML.</div>
            <p className="trust-item-body">
              A validation layer blocks writes across SQL, Mongo, and DuckDB. Connect to production — Byaan literally can't break it.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default TrustStrip;
