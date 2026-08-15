import Footer from "@/components/Footer";
import Header from "@/components/Header";

const sections = [
  {
    title: "Local-first by default",
    body: "The Byaan Mac app runs on your computer. Database credentials, queries, notebook content, and query results stay in your local environment unless you explicitly export or share them.",
  },
  {
    title: "Bring your own models",
    body: "Byaan connects to the AI model providers you configure. API keys are managed in your environment, and model traffic follows the provider and network settings you choose.",
  },
  {
    title: "Read-only data access",
    body: "Byaan is designed for analysis workflows and blocks known write operations such as DDL and DML before execution.",
  },
  {
    title: "Shared links",
    body: "When you create a shared notebook or dashboard link, the content needed for that share is made available through the share service. Remove shared links you no longer want available.",
  },
  {
    title: "Contact",
    body: "Questions about privacy, security, or team deployments can be sent to hello@byaan.ai.",
  },
];

const Privacy = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto max-w-4xl px-4 pt-28 pb-20">
        <section className="mb-14">
          <div className="mb-6 inline-flex rounded-full border border-primary/20 bg-primary/10 px-4 py-1.5">
            <span className="font-mono text-sm text-primary">Privacy</span>
          </div>
          <h1 className="mb-6 font-mono text-4xl font-bold leading-tight md:text-6xl">
            Your data stays under your control
          </h1>
          <p className="max-w-3xl text-lg leading-relaxed text-muted-foreground">
            Byaan is built for private data analysis. The desktop app is local-first, read-only
            by design, and intended to connect to the infrastructure and AI providers you choose.
          </p>
        </section>

        <section className="space-y-8">
          {sections.map((section) => (
            <article key={section.title} className="border-t border-border pt-8">
              <h2 className="mb-3 font-mono text-2xl font-bold">{section.title}</h2>
              <p className="leading-relaxed text-muted-foreground">{section.body}</p>
            </article>
          ))}
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default Privacy;
