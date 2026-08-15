import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, "../dist");

const SITE_URL = "https://www.byaan.ai";

const ROUTES = ["/", "/docs", "/privacy"];

const SEO = {
  "/": {
    title: "Byaan - Open-source AI Data Analyst for Slack, Mac, and MCP",
    description:
      "Byaan is an open-source AI data analyst for your databases. Ask in Slack, on your Mac, or via MCP from Claude Code and Cursor. Bring your own model, stay read-only by design, and self-host for teams.",
    path: "/",
    type: "website",
    structuredData: {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: "Byaan",
      url: `${SITE_URL}/`,
      description:
        "Open-source AI data analyst for databases. Ask questions in Slack, on Mac, or via MCP from Claude Code and Cursor. Builds organizational memory and reusable skills. Bring your own AI model. Read-only by design.",
      applicationCategory: "BusinessApplication",
      applicationSubCategory: "BusinessIntelligence, OpenSource",
      operatingSystem: "macOS, Linux, Web",
      license: "https://opensource.org/licenses/MIT",
      sameAs: ["https://github.com/byaan-ai/byaan"],
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
      featureList:
        "Slack integration, MCP server, multi-database support, bring your own AI model, read-only by design, organizational memory, reusable skills, interactive dashboards, self-hosted team deployment, open source",
    },
  },
  "/docs": {
    title: "Byaan Documentation - Open-source AI Data Analyst Setup",
    description:
      "Learn how to use Byaan with databases, uploaded files, Slack, MCP integrations, AI models, read-only analysis, dashboards, and self-hosted team deployments.",
    path: "/docs/",
    type: "article",
    structuredData: {
      "@context": "https://schema.org",
      "@type": "TechArticle",
      headline: "Byaan Documentation",
      url: `${SITE_URL}/docs/`,
      description:
        "Setup and feature documentation for Byaan, an open-source AI data analyst for databases, Slack, Mac, and MCP clients.",
      about: ["AI data analysis", "open source business intelligence", "Slack data analyst", "MCP"],
    },
  },
  "/privacy": {
    title: "Byaan Privacy - Local-First Data Analysis",
    description:
      "Byaan is local-first by default. Learn how credentials, queries, data, AI model access, and shared links are handled.",
    path: "/privacy/",
    type: "article",
    structuredData: {
      "@context": "https://schema.org",
      "@type": "WebPage",
      name: "Byaan Privacy",
      url: `${SITE_URL}/privacy/`,
      description:
        "Privacy information for Byaan, a local-first AI data analysis app for macOS.",
    },
  },
  "/404": {
    title: "Page Not Found - Byaan",
    description: "The requested Byaan page could not be found.",
    path: "/404",
    type: "website",
    robots: "noindex",
  },
};

function escapeAttribute(value) {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
}

function escapeHtml(value) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function absoluteUrl(route) {
  return route === "/" ? `${SITE_URL}/` : `${SITE_URL}${route}`;
}

function applySeo(html, route) {
  const seo = SEO[route] || SEO["/"];
  const url = absoluteUrl(seo.path);
  const image = `${SITE_URL}/og-image.png`;
  const structuredData = JSON.stringify(seo.structuredData || SEO["/"].structuredData, null, 2).replaceAll(
    "<",
    "\\u003c"
  );

  let next = html
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(seo.title)}</title>`)
    .replace(
      /<meta name="description" content="[^"]*" \/>/,
      `<meta name="description" content="${escapeAttribute(seo.description)}" />`
    )
    .replace(/<link rel="canonical" href="[^"]*" \/>/, `<link rel="canonical" href="${url}" />`)
    .replace(
      /<meta property="og:title" content="[^"]*" \/>/,
      `<meta property="og:title" content="${escapeAttribute(seo.title)}" />`
    )
    .replace(
      /<meta property="og:description" content="[^"]*" \/>/,
      `<meta property="og:description" content="${escapeAttribute(seo.description)}" />`
    )
    .replace(/<meta property="og:type" content="[^"]*" \/>/, `<meta property="og:type" content="${seo.type}" />`)
    .replace(/<meta property="og:image" content="[^"]*" \/>/, `<meta property="og:image" content="${image}" />`)
    .replace(/<meta property="og:url" content="[^"]*" \/>/, `<meta property="og:url" content="${url}" />`)
    .replace(
      /<meta name="twitter:title" content="[^"]*" \/>/,
      `<meta name="twitter:title" content="${escapeAttribute(seo.title)}" />`
    )
    .replace(
      /<meta name="twitter:description" content="[^"]*" \/>/,
      `<meta name="twitter:description" content="${escapeAttribute(seo.description)}" />`
    )
    .replace(/<meta name="twitter:image" content="[^"]*" \/>/, `<meta name="twitter:image" content="${image}" />`)
    .replace(
      /<script type="application\/ld\+json">[\s\S]*?<\/script>/,
      `<script type="application/ld+json">\n${structuredData}\n    </script>`
    );

  if (seo.robots) {
    next = next.replace("</head>", `    <meta name="robots" content="${seo.robots}" />\n  </head>`);
  }

  return next;
}

async function prerender() {
  const template = fs.readFileSync(path.join(distDir, "index.html"), "utf-8");
  const { render } = await import(path.join(distDir, "server/entry-server.js"));

  for (const route of ROUTES) {
    const appHtml = render(route);
    const html = applySeo(template.replace(
      '<div id="root"></div>',
      `<div id="root">${appHtml}</div>`
    ), route);

    const filePath =
      route === "/"
        ? path.join(distDir, "index.html")
        : path.join(distDir, route.slice(1), "index.html");

    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, html);
    console.log(`Pre-rendered: ${route} -> ${path.relative(distDir, filePath)}`);
  }

  const notFoundHtml = applySeo(
    template.replace('<div id="root"></div>', `<div id="root">${render("/404")}</div>`),
    "/404"
  );
  fs.writeFileSync(path.join(distDir, "404.html"), notFoundHtml);
  console.log("Pre-rendered: /404 -> 404.html");

  fs.rmSync(path.join(distDir, "server"), { recursive: true, force: true });
  console.log("Cleaned up server build artifacts");
}

prerender().catch((err) => {
  console.error("Pre-render failed:", err);
  process.exit(1);
});
