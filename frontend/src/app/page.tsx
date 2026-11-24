import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/common";
import { HeroScene } from "@/components/landing/hero-scene";
import { Button } from "@/components/ui/button";
import { InteractiveGrid } from "@/components/ui/interactive-grid";

const STEPS = [
  { title: "Create a room", body: "A private group for your family or friends. Invite them with a WhatsApp link." },
  { title: "Ask @Nazar", body: "In plain English or Hinglish. Nazar turns it into a watch and confirms in the chat." },
  { title: "Decide together", body: "When something changes, Nazar posts the numbers and sources. Everyone votes." },
];

const WATCHES = [
  { title: "Flight fares", body: "Route, date and a target price. Mark as booked to stop the watch." },
  { title: "Stocks", body: "NSE or BSE symbols, a % move or a price level, with a short explanation." },
  { title: "Government jobs", body: "New notices from official domains only. Anything unconfirmed is flagged." },
];

export default function LandingPage() {
  return (
    <div className="min-h-dvh overflow-x-clip bg-background">
      <header className="sticky top-0 z-30 bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
          <Logo />
          <nav className="flex items-center gap-1">
            <a href="#how" className="hidden px-3 py-2 text-[14px] text-muted-foreground hover:text-foreground sm:block">
              How it works
            </a>
            <Button variant="ghost" asChild>
              <Link href="/login">Log in</Link>
            </Button>
            <Button asChild>
              <Link href="/register">Get started</Link>
            </Button>
          </nav>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden">
          <InteractiveGrid cellSize={48} className="text-primary [mask-image:radial-gradient(700px_circle_at_50%_30%,white,transparent)]" />
          <div className="relative mx-auto max-w-6xl px-5 pb-24 pt-20 text-center sm:px-8 sm:pt-28">
            <h1 className="mx-auto max-w-3xl text-[44px] font-semibold leading-[1.04] tracking-[-0.04em] sm:text-[68px]">
              You live your life.
              <br />
              <span className="font-serif text-[1.08em] font-normal italic tracking-[-0.02em] text-primary">Nazar keeps an eye.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-[17px] leading-relaxed text-muted-foreground">
              An assistant in your family group chat that watches flight fares, stocks and government job notices, and tells everyone when something changes.
            </p>
            <div className="mt-9 flex justify-center gap-3">
              <Button size="lg" asChild>
                <Link href="/register">
                  Get started <ArrowRight />
                </Link>
              </Button>
              <Button size="lg" variant="secondary" asChild>
                <a href="#how">How it works</a>
              </Button>
            </div>
            <div className="mt-20">
              <HeroScene />
            </div>
          </div>
        </section>

        <section id="how" className="border-t border-border">
          <div className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
            <h2 className="max-w-md text-[32px] font-semibold leading-tight tracking-[-0.03em]">Not a chatbot. A watcher that reports to your group.</h2>
            <ol className="mt-14 grid gap-10 md:grid-cols-3">
              {STEPS.map((s, i) => (
                <li key={s.title}>
                  <p className="text-[13px] tabular-nums text-subtle">0{i + 1}</p>
                  <h3 className="mt-3 text-[17px] font-semibold">{s.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t border-border">
          <div className="mx-auto max-w-6xl px-5 py-24 sm:px-8">
            <h2 className="max-w-md text-[32px] font-semibold leading-tight tracking-[-0.03em]">What Nazar watches</h2>
            <div className="mt-14 grid gap-px overflow-hidden rounded-[16px] border border-border bg-border md:grid-cols-3">
              {WATCHES.map((w) => (
                <div key={w.title} className="bg-surface p-7">
                  <h3 className="text-[17px] font-semibold">{w.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{w.body}</p>
                </div>
              ))}
            </div>
            <p className="mt-8 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
              Every alert links to its source. If a check fails or a notice can&apos;t be confirmed, Nazar says so instead of guessing.
            </p>
          </div>
        </section>

        <section className="border-t border-border">
          <div className="mx-auto max-w-6xl px-5 py-24 text-center sm:px-8">
            <h2 className="text-[36px] font-semibold tracking-[-0.03em]">
              Stop refreshing. <span className="font-serif font-normal italic text-primary">Start a room.</span>
            </h2>
            <Button size="lg" className="mt-8" asChild>
              <Link href="/register">
                Get started <ArrowRight />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-8 text-[13px] text-subtle sm:flex-row sm:px-8">
          <Logo />
          <p>You live your life. Nazar keeps an eye.</p>
        </div>
      </footer>
    </div>
  );
}
