import posthog from "posthog-js";

type CtaLocation =
  | "header"
  | "hero"
  | "cta_section"
  | "self_host"
  | "download_button"
  | "faq";

type Architecture = "apple-silicon" | "intel" | "unknown";

export function trackDownloadClick(props: {
  location: CtaLocation;
  arch: Architecture;
  url: string;
  is_mac: boolean;
}) {
  if (typeof window === "undefined") return;
  posthog.capture("download_clicked", props);
}

export function trackCtaClick(props: {
  cta:
    | "github"
    | "github_discussions"
    | "selfhost_docs"
    | "docs"
    | "star_github"
    | "contact_email";
  location: CtaLocation;
  url?: string;
}) {
  if (typeof window === "undefined") return;
  posthog.capture("cta_clicked", props);
}
