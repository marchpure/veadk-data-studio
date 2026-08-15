import { useDownload } from "@/hooks/useDownload";
import { DownloadIcon, DockerIcon, GithubIcon } from "@/components/landing/icons";
import { trackCtaClick, trackDownloadClick } from "@/lib/analytics";

const GITHUB_URL = "https://github.com/byaan-ai/byaan";

const CTA = () => {
  const { isMac, architecture, appleUrl, intelUrl } = useDownload();
  const downloadUrl = architecture === "apple-silicon" ? appleUrl : intelUrl;
  const macHref = isMac && architecture !== "unknown" && downloadUrl ? downloadUrl : appleUrl;

  return (
    <section className="final-cta" id="download">
      <div className="container">
        <div className="section-head reveal">
          <h2 className="section-title">Three ways to start with Byaan</h2>
          <p className="section-sub">
            Pick the path that fits how you work today. You can switch later — your skills come with you.
          </p>
        </div>

        <div className="final-grid">
          <div className="path-card primary reveal">
            <div className="path-eyebrow">Individuals</div>
            <div className="path-icon">
              <DownloadIcon size={22} />
            </div>
            <div className="path-title">Download for Mac</div>
            <p className="path-body">
              Free. MIT-licensed. Runs on your Mac. No signup, no cloud account, no telemetry on your data.
            </p>
            <a
              className="btn btn-primary btn-lg"
              href={macHref}
              onClick={() =>
                trackDownloadClick({
                  location: "cta_section",
                  arch: architecture,
                  url: macHref,
                  is_mac: isMac,
                })
              }
            >
              Download for Mac →
            </a>
          </div>

          <div className="path-card reveal">
            <div className="path-eyebrow">Teams</div>
            <div className="path-icon">
              <DockerIcon size={22} />
            </div>
            <div className="path-title">Team Version</div>
            <p className="path-body">
              One-line install for your team. Multi-user auth, RBAC, Slack, and HTTPS — out of the box.
            </p>
            <a
              className="btn btn-outline btn-lg"
              href="/docs"
              onClick={() => trackCtaClick({ cta: "selfhost_docs", location: "cta_section", url: "/docs" })}
            >
              Team version docs →
            </a>
          </div>

          <div className="path-card reveal">
            <div className="path-eyebrow">Builders</div>
            <div className="path-icon">
              <GithubIcon size={22} />
            </div>
            <div className="path-title">Follow on GitHub</div>
            <p className="path-body">
              Track development, file issues, and join discussions. Watch the repo to stay close to what we're shipping.
            </p>
            <a
              className="btn btn-outline btn-lg"
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => trackCtaClick({ cta: "github", location: "cta_section", url: GITHUB_URL })}
            >
              View on GitHub →
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTA;
