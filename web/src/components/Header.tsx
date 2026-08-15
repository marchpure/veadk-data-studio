import { useLocation } from "react-router-dom";
import { useDownload } from "@/hooks/useDownload";
import byaanLogo from "@/assets/byaan-logo-orange.png";
import { GithubIcon, DownloadIcon } from "@/components/landing/icons";
import { trackCtaClick, trackDownloadClick } from "@/lib/analytics";

const GITHUB_URL = "https://github.com/byaan-ai/byaan";

const Header = () => {
  const { isMac, architecture, appleUrl, intelUrl } = useDownload();
  const { pathname } = useLocation();
  const isHome = pathname === "/";
  const sectionHref = (id: string) => (isHome ? `#${id}` : `/#${id}`);
  const canShowDownload = isMac && architecture !== "unknown";
  const downloadUrl = architecture === "apple-silicon" ? appleUrl : intelUrl;
  const headerDownloadHref = canShowDownload ? downloadUrl : sectionHref("download");

  return (
    <div className="byaan-landing">
    <header className="site">
      <div className="container nav">
        <a className="brand" href="/">
          <img src={byaanLogo} alt="Byaan" />
          <span className="brand-name">byaan</span>
        </a>
        <nav className="nav-links">
          <a href={sectionHref("features")}>Features</a>
          <a href={sectionHref("how-it-works")}>How it works</a>
          <a href={sectionHref("self-host")}>Team Version</a>
          <a href="/docs">Docs</a>
          <a href={sectionHref("faq")}>FAQ</a>
        </nav>
        <div className="nav-cta">
          <a
            className="btn btn-outline"
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => trackCtaClick({ cta: "github", location: "header", url: GITHUB_URL })}
          >
            <GithubIcon size={14} />
            GitHub
          </a>
          <a
            className="btn btn-primary"
            href={headerDownloadHref}
            onClick={() =>
              trackDownloadClick({
                location: "header",
                arch: architecture,
                url: headerDownloadHref,
                is_mac: isMac,
              })
            }
          >
            <DownloadIcon size={14} />
            Download
          </a>
        </div>
      </div>
    </header>
    </div>
  );
};

export default Header;
