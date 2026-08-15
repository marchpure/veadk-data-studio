import { useLocation } from "react-router-dom";
import byaanLogo from "@/assets/byaan-logo-orange.png";
import { GithubIcon } from "@/components/landing/icons";

const GITHUB_URL = "https://github.com/byaan-ai/byaan";

const Footer = () => {
  const { pathname } = useLocation();
  const isHome = pathname === "/";
  const sectionHref = (id: string) => (isHome ? `#${id}` : `/#${id}`);

  return (
    <div className="byaan-landing">
    <footer className="site">
      <div className="container">
        <div className="footer-top">
          <a className="brand" href="/">
            <img src={byaanLogo} alt="Byaan" />
            <span className="brand-name">byaan</span>
          </a>
          <nav className="footer-nav">
            <a href={sectionHref("features")}>Features</a>
            <a href={sectionHref("how-it-works")}>How it works</a>
            <a href={sectionHref("self-host")}>Team Version</a>
            <a href="/docs">Docs</a>
            <a href={sectionHref("faq")}>FAQ</a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              <GithubIcon size={13} />
              GitHub
            </a>
            <a href="/privacy">Privacy</a>
            <a href={`${GITHUB_URL}/blob/main/LICENSE`} target="_blank" rel="noopener noreferrer">
              License
            </a>
          </nav>
        </div>
        <div className="footer-bottom">
          © {new Date().getFullYear()} Byaan · Mac app MIT-licensed · Team version AGPL
        </div>
      </div>
    </footer>
    </div>
  );
};

export default Footer;
