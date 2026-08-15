import { useEffect } from "react";
import Header from "@/components/Header";
import Hero from "@/components/Hero";
import TrustStrip from "@/components/TrustStrip";
import WhyByaan from "@/components/WhyByaan";
import HowItWorks from "@/components/HowItWorks";
import Features from "@/components/Features";
import SelfHost from "@/components/SelfHost";
import FAQ from "@/components/FAQ";
import CTA from "@/components/CTA";
import Footer from "@/components/Footer";
const Index = () => {
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("visible");
            io.unobserve(e.target);
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.05 }
    );
    document.querySelectorAll(".byaan-landing .reveal").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="byaan-landing byaan-page">
      <div className="bg-grid"></div>
      <div className="bg-glow"></div>
      <div className="bg-glow-2"></div>
      <Header />
      <main>
        <Hero />
        <TrustStrip />
        <WhyByaan />
        <HowItWorks />
        <Features />
        <SelfHost />
        <FAQ />
        <CTA />
      </main>
      <Footer />
    </div>
  );
};

export default Index;
