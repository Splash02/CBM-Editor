const { useEffect, useRef, useState } = React;
const { createRoot } = ReactDOM;

document.documentElement.classList.add("js");

const html = htm.bind(React.createElement);
const REPO = "https://github.com/Splash02/CBM-Editor";
const RELEASES = `${REPO}/releases`;
const STEAM = "https://store.steampowered.com/app/2240620/UNBEATABLE/";
const DISCORD = "https://discord.com/invite/XzqMhRMmhC";
const IMG = "https://raw.githubusercontent.com/Splash02/CBM-Editor/main/images";

const Arrow = ({ className = "" }) => html`
    <svg className=${className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 18 18 6M8 6h10v10" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  `;

const MenuIcon = ({ close = false }) => html`
    <span className="relative block size-6" aria-hidden="true">
      <span className=${`menu-line ${close ? "top-[11px] rotate-45" : "top-[5px]"}`}></span>
      <span className=${`menu-line top-[11px] ${close ? "opacity-0" : "opacity-100"}`}></span>
      <span className=${`menu-line ${close ? "top-[11px] -rotate-45" : "top-[17px]"}`}></span>
    </span>
  `;

function TextLink({ href, children }) {
  return html`
      <a
        href=${href}
        target="_blank"
        rel="noreferrer"
        className="hover-arrow font-unbeatable inline-flex items-center justify-between gap-8 border-b border-white/30 pb-2 text-sm uppercase tracking-[0.1em] hover:border-white"
      >
        <span>${children}</span><span aria-hidden="true">↗</span>
      </a>
    `;
}

function Nav() {
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);
  const links = [["editor", "#editor"], ["styles", "#styles"], ["UNBEATABLE", "#game"], ["community", "#community"]];

  useEffect(() => {
    const firstScreen = document.getElementById("top");
    if (!firstScreen) return undefined;

    const heroWatcher = new IntersectionObserver(([entry]) => {
      const shouldShow = !entry.isIntersecting;
      setVisible(shouldShow);
      if (!shouldShow) setOpen(false);
    }, { threshold: 0 });

    heroWatcher.observe(firstScreen);
    return () => heroWatcher.disconnect();
  }, []);

  return html`
      <header className=${`fixed inset-x-0 top-0 z-50 border-b border-white/15 bg-ink/92 backdrop-blur-lg transition-[transform,opacity] duration-300 ease-out ${visible ? "translate-y-0 opacity-100" : "pointer-events-none -translate-y-full opacity-0"}`}>
        <nav className="mx-auto flex h-16 max-w-[1600px] items-center justify-between px-4 sm:h-[4.5rem] sm:px-7" aria-label="Main navigation">
          <a href="#top" aria-label="CBM Editor" className="flex items-center gap-1">
            <img src=${`${IMG}/CBM_Editor_Icon.png`} alt="" width="500" height="500" className="size-10 object-cover" />
            <span className="font-logo text-2xl uppercase leading-none tracking-[-.04em] text-paper">Editor</span>
          </a>

          <div className="font-unbeatable hidden items-center gap-7 text-sm uppercase tracking-[0.1em] md:flex">
            ${links.map(([label, href]) => html`<a href=${href} className="nav-tab hover:text-pink">${label}</a>`)}
            <a href=${RELEASES} target="_blank" rel="noreferrer" className="nav-download px-5 py-2"><span>download <b aria-hidden="true">↗</b></span></a>
          </div>

          <button
            type="button"
            className="grid size-10 place-items-center border border-white/20 transition-colors duration-200 hover:border-pink hover:text-pink md:hidden"
            aria-label=${open ? "Close navigation" : "Open navigation"}
            aria-expanded=${open}
            onClick=${() => setOpen(!open)}
          >
            <${MenuIcon} close=${open} />
          </button>
        </nav>

        <div className=${`grid overflow-hidden bg-ink transition-[grid-template-rows,opacity] duration-300 ease-out md:hidden ${open ? "grid-rows-[1fr] border-t border-white/15 opacity-100" : "grid-rows-[0fr] border-t border-transparent opacity-0"}`}>
          <div className="min-h-0">
            <div className="px-4 pb-5">
              ${links.map(([label, href]) => html`
                <a href=${href} onClick=${() => setOpen(false)} className="font-unbeatable block border-b border-white/10 py-3.5 text-base uppercase tracking-[0.1em] transition-colors hover:text-pink">${label}</a>
              `)}
              <a href=${RELEASES} target="_blank" rel="noreferrer" className="nav-download font-unbeatable mt-4 block px-5 py-3 text-base uppercase tracking-[0.1em]"><span className="justify-between">download <b aria-hidden="true">↗</b></span></a>
            </div>
          </div>
        </div>
      </header>
    `;
}

function Hero() {
  return html`
      <section id="top" className="site-grid relative overflow-hidden border-b border-white/15">
        <div className="graphic-cluster graphic-hero" aria-hidden="true"></div>
        <div className="shape-scrap scrap-a left-[3%] top-[8%] h-14 w-[22%] -rotate-6 bg-paper/10 sm:h-20" aria-hidden="true"></div>
        <div className="shape-scrap scrap-d tone-shift bottom-[7%] right-[24%] h-24 w-[14%] rotate-6" aria-hidden="true"></div>
        <div className="relative z-10 mx-auto grid min-h-svh max-w-[1600px] -translate-y-[1vh] content-start items-center gap-5 px-4 pb-6 pt-[6vh] sm:-translate-y-[3vh] sm:gap-7 sm:px-7 sm:pb-10 sm:pt-[6vh] lg:grid-cols-[.7fr_1.3fr] lg:content-center lg:gap-0 lg:py-10">
          <div className="relative z-20">
            <h1 aria-label="CBM Editor" className="hero-lockup reveal-layer relative mx-auto w-[72vw] max-w-[390px] uppercase leading-[0.72] tracking-[-0.055em] sm:w-[52vw] lg:mx-0 lg:w-[27vw] lg:max-w-[430px]" data-reveal="" data-delay="1">
              <span className="relative block aspect-square">
                <img src=${`${IMG}/CBM_Editor_Icon.png`} alt="" width="500" height="500" fetchPriority="high" className="block size-full object-contain" />
              </span>
              <span className="editor-mark absolute z-30 block w-max whitespace-nowrap" data-text="EDITOR">EDITOR</span>
            </h1>
            <div className="reveal-layer mt-5 max-w-md border-l-4 border-pink pl-4 sm:mt-7 sm:pl-5" data-reveal="">
              <p className="font-unbeatable text-lg leading-7 tracking-[.02em] text-white/75 sm:text-xl sm:leading-8">
                Highly customizable beatmap editor made for UNBEATABLE
              </p>
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-4 sm:mt-6 sm:gap-x-8 sm:gap-y-5">
                <${TextLink} href=${RELEASES}>download<//>
                <${TextLink} href=${REPO}>source on github<//>
              </div>
            </div>
          </div>

          <div className="reveal-layer relative w-full lg:-ml-8 lg:max-w-[980px]" data-reveal="" data-delay="1">
            <div className="absolute -inset-3 -rotate-2 bg-pink/35 [clip-path:polygon(4%_0,100%_7%,96%_100%,0_91%)]" aria-hidden="true"></div>
            <div className="hero-shot relative overflow-hidden border-2 border-paper bg-paper p-1.5 sm:p-2">
              <img
                src=${`${IMG}/screenshot_5.png`}
                alt="CBM Editor chart timeline with waveform, notes, events and preview"
                width="2067"
                height="1127"
                fetchPriority="high"
                className="block h-auto w-full"
              />
            </div>
          </div>
        </div>
      </section>
    `;
}

function WorkflowThingy() {
  return html`
      <div className="border-b border-ink bg-lilac text-ink">
        <div className="h-16 overflow-hidden border-b border-ink bg-ink sm:h-20" aria-hidden="true">
          <div className="wave-track h-full w-full" style=${{ backgroundImage: `url(${IMG}/screenshot_6.png)` }}></div>
        </div>
        <div className="mx-auto grid max-w-[1600px] grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          ${["Create Project", "Add Resources", "Synchronize Timing", "Chart The Beatmap", "Preview", "Export"].map((item, index) => html`
            <div className="font-unbeatable flex min-h-16 items-center gap-3 border-b border-r border-ink/25 px-4 text-xs uppercase leading-5 tracking-[0.08em] sm:min-h-20 lg:border-b-0">
              <span className="text-ink/35">${String(index + 1).padStart(2, "0")}</span><span>${item}</span>
            </div>
          `)}
        </div>
      </div>
    `;
}

const editorTutorialStuffIdkWhatToCallThis = [
  { title: "projects", text: "Start a new project, open an existing chart, choose its difficulty and export the finished beatmap.", image: "screenshot_12.png", width: 430, height: 367 },
  { title: "metadata & resources", text: "Set the song information and connect the audio, cover art and other files the chart needs.", image: "screenshot_11.png", width: 437, height: 727 },
  { title: "timing", text: "Match the timeline to the song with BPM changes, beat grids and triplet divisions.", image: "screenshot_9.png", width: 407, height: 100 },
  { title: "charting", text: "Place notes, holds, brawls and events in their exact execution order.", image: "screenshot_8.png", width: 1561, height: 107 },
  { title: "preview", text: "Play the chart inside the editor and check lane placement, selections and timing.", image: "screenshot_10.png", width: 655, height: 275 },
  { title: "interface", text: "Tune colors, backgrounds, visibility, grids and the audio visualizer however you want", image: "screenshot_13.png", width: 620, height: 961 },
];

function EditorSection() {
  return html`
      <section id="editor" className="paper-grid relative scroll-mt-16 overflow-hidden bg-paper text-ink sm:scroll-mt-[4.5rem]">
        <div className="font-accent pointer-events-none absolute left-1/2 -top-4 z-0 -translate-x-1/2 whitespace-nowrap text-[clamp(5.5rem,24vw,23rem)] uppercase leading-none tracking-[-.06em] text-ink/[.045]" aria-hidden="true">EDITOR</div>
        <div className="graphic-cluster graphic-paper" aria-hidden="true"></div>
        <div className="shape-scrap scrap-b right-[3%] top-[18%] h-20 w-[17%] rotate-12 bg-pink/15" aria-hidden="true"></div>
        <div className="shape-scrap scrap-c bottom-[28%] right-[-6%] h-[220px] w-[220px] rotate-12 bg-ink/[.07] sm:h-[320px] sm:w-[320px]" aria-hidden="true"></div>
        <div className="shape-scrap scrap-f tone-shift left-[7%] top-[46%] h-24 w-[13%] -rotate-6" aria-hidden="true"></div>
        <div className="shape-scrap scrap-g bottom-[1.5%] left-[-3%] hidden h-[245px] w-[390px] -rotate-6 lg:block" aria-hidden="true"></div>
        <div className="relative z-10 mx-auto max-w-[1600px] px-4 py-12 sm:px-7 sm:py-20 lg:py-24">
          <div className="relative py-2 sm:py-8">
            <div className="font-unbeatable text-sm uppercase tracking-[0.12em] text-ink/50">
              <p>01 / editor</p>
              <p className="mt-2">interface & tools</p>
            </div>
            <div className="reveal-layer mt-6 sm:ml-[12%] sm:mt-2" data-reveal="">
              <h2 className="whitespace-nowrap font-display text-[clamp(3.25rem,15vw,10.5rem)] uppercase leading-[0.82] tracking-[-0.045em]">
                THE <span className="outline-ink">EDITOR</span>
              </h2>
              <p className="font-unbeatable mt-5 max-w-2xl text-sm uppercase leading-6 tracking-[.1em] text-ink/60 sm:text-base">
                Timeline / project select / metadata / resources / settings
              </p>
            </div>
          </div>

          <div className="reveal-layer relative ml-auto mt-8 w-[94%] max-w-[940px] sm:mt-10 sm:w-[86%] lg:mt-12" data-reveal="">
            <div className="-rotate-[.45deg]">
              <img
                src=${`${IMG}/screenshot_7.png`}
                alt="CBM Editor project selection view with chart covers"
                width="2560"
                height="1380"
                loading="lazy"
                className="editor-overview w-full border border-ink object-cover"
              />
            </div>
          </div>

          <div className="mt-9 space-y-8 border-t border-ink/25 pt-7 sm:mt-11 sm:space-y-10 sm:pt-8 lg:mt-14 lg:space-y-12 lg:pt-10">
            ${editorTutorialStuffIdkWhatToCallThis.map((feature, index) => html`
              <article className=${`reveal-layer relative flex flex-col items-center gap-4 border-b border-ink/20 pb-7 sm:gap-6 sm:pb-9 lg:gap-8 lg:pb-10 ${index % 2 ? "lg:ml-auto lg:w-[88%] lg:flex-row-reverse" : "lg:w-[90%] lg:flex-row"}`} data-reveal="" data-delay=${String(index % 3)}>
                <div className="relative z-10 w-full lg:w-[31%]">
                  <span className="font-logo text-5xl leading-none text-pink sm:text-6xl">0${index + 1}</span>
                  <h3 className="font-unbeatable mt-2 text-base uppercase tracking-[.12em] sm:text-lg">${feature.title}</h3>
                  <p className="font-unbeatable mt-3 max-w-md text-lg leading-6 tracking-[.015em] text-ink/60">${feature.text}</p>
                </div>
                <figure className=${`relative z-10 flex w-full items-center ${[2, 3, 4].includes(index) ? "lg:w-[64%]" : "lg:w-[48%]"}`}>
                  <div className="absolute -inset-3 -z-10 rotate-1 bg-pink/[.14] [clip-path:polygon(3%_0,100%_8%,96%_100%,0_91%)]" aria-hidden="true"></div>
                  <div className="flex w-full items-center justify-center overflow-hidden border border-ink/30 bg-[#1d1d20] p-2 shadow-[7px_7px_0_rgba(17,17,17,.18)] sm:p-3">
                    <img src=${`${IMG}/${feature.image}`} alt=${`${feature.title} controls in CBM Editor`} width=${feature.width} height=${feature.height} loading="lazy" className="h-auto max-h-[350px] w-auto max-w-full object-contain" />
                  </div>
                </figure>
              </article>
            `)}
          </div>
        </div>
      </section>
    `;
}

const styleShots = [
  { file: "screenshot_1.png", label: "full timeline / dark" },
  { file: "screenshot_4.png", label: "clipboard / light setup" },
  { file: "screenshot_2.png", label: "custom color setup" },
];

function StyleStuff() {
  const [active, setActive] = useState(null);

  useEffect(() => {
    if (!active) return;
    const onKey = (event) => event.key === "Escape" && setActive(null);
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [active]);

  return html`
      <section id="styles" className="relative scroll-mt-16 overflow-hidden bg-pink text-ink sm:scroll-mt-[4.5rem]">
        <div className="graphic-cluster graphic-styles" aria-hidden="true"></div>
        <div className="shape-scrap scrap-b tone-shift bottom-[38%] right-[5%] h-24 w-[12%] -rotate-12" aria-hidden="true"></div>
        <div className="relative z-10 mx-auto max-w-[1600px] px-4 py-12 sm:px-7 sm:py-20 lg:py-24">
          <div className="grid items-end gap-8 lg:grid-cols-[1.35fr_.65fr]">
            <h2 className="reveal-layer font-display text-[clamp(3.6rem,14vw,13rem)] uppercase leading-[0.8] tracking-[-0.08em]" data-reveal="">
              <span className="inline-block -skew-x-6">STYLES</span>
            </h2>
            <p className="font-unbeatable max-w-sm border-l border-ink/40 pl-5 text-sm uppercase leading-5 tracking-[0.1em] lg:mb-2">
              02 / interface styles
            </p>
          </div>

          <div className="relative mt-8 grid grid-cols-1 gap-5 sm:mt-10 sm:gap-7 lg:grid-cols-2 lg:items-start lg:gap-x-8 lg:gap-y-7">
            <div className="pointer-events-none absolute bottom-[3%] left-[-3%] z-0 hidden w-[20%] -rotate-6 lg:block" aria-hidden="true">
              <p className="font-accent text-[clamp(4rem,5vw,6rem)] uppercase leading-[.68] text-ink/[.22]">MAKE</p>
              <p className="font-logo mt-3 bg-ink px-3 py-2 text-[clamp(1.2rem,2vw,2.3rem)] uppercase leading-none text-paper">IT YOURS</p>
              <div className="mt-4 h-16 bg-paper/35 [clip-path:polygon(0_20%,100%_0,82%_100%,8%_82%)]"></div>
            </div>
            <div className="pointer-events-none absolute bottom-[29%] left-[2%] z-0 hidden h-14 w-[14%] rotate-6 bg-ink/10 [clip-path:polygon(8%_0,100%_18%,84%_100%,0_72%)] lg:block" aria-hidden="true"></div>
            <div className="pointer-events-none absolute bottom-[31%] right-[2%] z-0 hidden h-16 w-[15%] -rotate-6 bg-paper/35 [clip-path:polygon(0_14%,88%_0,100%_76%,14%_100%)] lg:block" aria-hidden="true"></div>
            <div className="pointer-events-none absolute bottom-[1%] right-[13%] z-0 hidden h-8 w-[9%] rotate-12 bg-ink/15 [clip-path:polygon(12%_0,100%_20%,84%_100%,0_74%)] lg:block" aria-hidden="true"></div>
            <div className="pointer-events-none absolute bottom-[2%] right-[-4%] z-0 hidden w-[18%] rotate-6 lg:block" aria-hidden="true">
              <div className="style-dots aspect-square rounded-full border-[clamp(10px,1.5vw,22px)] border-ink/15"></div>
              <p className="font-unbeatable absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 -rotate-12 bg-paper px-3 py-2 text-[clamp(1.2rem,1.8vw,2rem)] uppercase leading-none tracking-[.08em]">CUSTOM</p>
            </div>
            ${styleShots.map((shot, index) => html`
              <button
                type="button"
                className=${`style-shot reveal-layer group relative z-10 block text-left ${index === 0 ? "w-[96%] lg:w-full" : index === 1 ? "angle-right ml-auto w-[92%] lg:mt-10 lg:w-full" : "angle-left w-[90%] justify-self-center lg:col-span-2 lg:w-[58%]"}`}
                data-reveal=""
                data-delay=${String(index % 3)}
                onClick=${() => setActive(shot)}
                aria-label=${`Open ${shot.label}`}
              >
                <div className=${`pointer-events-none absolute -inset-2 -z-10 bg-paper/35 ${index % 2 ? "rotate-2" : "-rotate-2"} [clip-path:polygon(3%_0,100%_6%,96%_100%,0_92%)]`} aria-hidden="true"></div>
                <div className="overflow-hidden border-2 border-ink bg-ink p-1 shadow-[9px_9px_0_rgba(17,17,17,.32)] sm:p-2 sm:shadow-[13px_13px_0_rgba(17,17,17,.32)]">
                  <img
                    src=${`${IMG}/${shot.file}`}
                    alt=${`CBM Editor — ${shot.label}`}
                    width="2560"
                    height="1380"
                    loading="lazy"
                    className="block h-auto w-full object-contain"
                  />
                </div>
              </button>
            `)}
          </div>
        </div>

        ${active && html`
          <div className="fixed inset-0 z-[80] grid place-items-center overflow-hidden bg-black/92 p-3 backdrop-blur-sm sm:p-8" role="dialog" aria-modal="true" aria-label="Screenshot preview" onClick=${() => setActive(null)}>
            <div className="relative inline-flex w-fit max-w-full items-center justify-center" onClick=${(event) => event.stopPropagation()}>
              <img src=${`${IMG}/${active.file}`} alt=${active.label} className="block max-h-[calc(100dvh-1.5rem)] max-w-[calc(100vw-1.5rem)] object-contain sm:max-h-[calc(100dvh-4rem)] sm:max-w-[calc(100vw-4rem)]" />
              <button type="button" onClick=${() => setActive(null)} className="modal-close absolute right-2 top-2 z-10 grid size-11 place-items-center sm:right-3 sm:top-3 sm:size-14" aria-label="Close screenshot"><${MenuIcon} close=${true} /></button>
            </div>
          </div>
        `}
      </section>
    `;
}

let youtubeApiRequest;

function getYouTubeApi() {
  if (globalThis.YT?.Player) return Promise.resolve(globalThis.YT);

  if (!youtubeApiRequest) {
    youtubeApiRequest = new Promise((resolve, reject) => {
      const previousReadyHandler = globalThis.onYouTubeIframeAPIReady;
      globalThis.onYouTubeIframeAPIReady = () => {
        previousReadyHandler?.();
        resolve(globalThis.YT);
      };

      const existingScript = document.querySelector('script[src="https://www.youtube.com/iframe_api"]');
      if (!existingScript) {
        const apiScript = document.createElement("script");
        apiScript.src = "https://www.youtube.com/iframe_api";
        apiScript.async = true;
        apiScript.onerror = () => {
          youtubeApiRequest = undefined;
          reject(new Error("YouTube player API could not be loaded"));
        };
        document.head.append(apiScript);
      }
    });
  }

  return youtubeApiRequest;
}

function Trailer() {
  const [started, setStarted] = useState(false);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(80);
  const playerMount = useRef(null);
  const player = useRef(null);

  useEffect(() => {
    if (!started || !playerMount.current) return undefined;

    let disposed = false;
    const playerVars = {
      autoplay: 1,
      controls: 0,
      cc_load_policy: 0,
      disablekb: 1,
      fs: 0,
      iv_load_policy: 3,
      playsinline: 1,
      rel: 0,
      vq: "highres",
      widget_referrer: "https://splash02.github.io/CBM-Editor/",
    };

    if (window.location.protocol !== "file:") playerVars.origin = window.location.origin;

    getYouTubeApi().then((YT) => {
      if (disposed || !playerMount.current) return;

      player.current = new YT.Player(playerMount.current, {
        width: "100%",
        height: "100%",
        videoId: "XwKFOZeJukA",
        playerVars,
        events: {
          onReady: (event) => {
            if (disposed) return;
            event.target.setVolume(volume);
            setDuration(event.target.getDuration());
            setReady(true);
            event.target.playVideo();
          },
          onStateChange: (event) => {
            setPlaying(event.data === YT.PlayerState.PLAYING);
            setCurrentTime(event.target.getCurrentTime());
            setDuration(event.target.getDuration());
          },
        },
      });
    }).catch(() => setReady(false));

    return () => {
      disposed = true;
      player.current?.destroy();
      player.current = null;
    };
  }, [started]);

  useEffect(() => {
    if (!ready) return undefined;

    const progressClock = window.setInterval(() => {
      if (!player.current) return;
      setCurrentTime(player.current.getCurrentTime());
      setDuration(player.current.getDuration());
    }, 250);

    return () => window.clearInterval(progressClock);
  }, [ready]);

  const togglePlayback = () => {
    if (!player.current) return;
    if (playing) player.current.pauseVideo();
    else player.current.playVideo();
  };

  const stopPlayback = () => {
    if (!player.current) return;
    player.current.stopVideo();
    setPlaying(false);
    setCurrentTime(0);
  };

  const seek = (event) => {
    const nextTime = Number(event.target.value);
    player.current?.seekTo(nextTime, true);
    setCurrentTime(nextTime);
  };

  const changeVolume = (event) => {
    const nextVolume = Number(event.target.value);
    player.current?.setVolume(nextVolume);
    setVolume(nextVolume);
  };

  const progressFill = duration ? `${(currentTime / duration) * 100}%` : "0%";

  return html`
      <div>
        <div className="trailer-frame relative aspect-video overflow-hidden border-2 border-paper bg-black shadow-[10px_10px_0_#df396e] transition-transform duration-500 hover:rotate-0 sm:shadow-[14px_14px_0_#df396e]">
          ${started ? html`
            <div className="absolute inset-0">
              <div ref=${playerMount} className="size-full"></div>
            </div>
            <div className=${`custom-player-controls absolute inset-x-2 bottom-2 z-20 flex items-center gap-2 border border-paper/35 bg-ink/95 p-2 shadow-[5px_5px_0_#df396e] sm:inset-x-4 sm:bottom-4 sm:gap-3 sm:p-3 ${ready ? "is-ready" : ""}`}>
              <button type="button" onClick=${togglePlayback} disabled=${!ready} className="grid size-9 shrink-0 place-items-center border border-paper/60 text-paper transition-colors hover:border-pink hover:bg-pink hover:text-ink sm:size-10" aria-label=${playing ? "Pause trailer" : "Play trailer"}>
                ${playing ? html`
                  <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden="true"><path d="M6 5h4v14H6V5Zm8 0h4v14h-4V5Z" /></svg>
                ` : html`
                  <svg viewBox="0 0 24 24" className="ml-0.5 size-4" fill="currentColor" aria-hidden="true"><path d="m8 5 11 7-11 7V5Z" /></svg>
                `}
              </button>
              <button type="button" onClick=${stopPlayback} disabled=${!ready} className="grid size-9 shrink-0 place-items-center border border-paper/60 text-paper transition-colors hover:border-pink hover:bg-pink hover:text-ink sm:size-10" aria-label="Stop trailer">
                <span className="block size-3 bg-current" aria-hidden="true"></span>
              </button>
              <input type="range" min="0" max=${Math.max(duration, 0.1)} step="0.1" value=${Math.min(currentTime, duration || 0)} onInput=${seek} className="player-slider min-w-0 flex-1" style=${{ "--fill": progressFill }} aria-label="Trailer playback position" />
              <div className="flex w-[76px] shrink-0 items-center gap-2 sm:w-[116px]">
                ${volume === 0 ? html`
                  <svg viewBox="0 0 24 24" className="size-4 shrink-0 text-paper" fill="none" aria-hidden="true"><path d="M4 10v4h4l5 4V6L8 10H4Zm12-1 5 5m0-5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" /></svg>
                ` : volume < 50 ? html`
                  <svg viewBox="0 0 24 24" className="size-4 shrink-0 text-paper" fill="none" aria-hidden="true"><path d="M4 10v4h4l5 4V6L8 10H4Zm12-1.5c1.25 1.18 1.25 5.82 0 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" /></svg>
                ` : html`
                  <svg viewBox="0 0 24 24" className="size-4 shrink-0 text-paper" fill="none" aria-hidden="true"><path d="M4 10v4h4l5 4V6L8 10H4Zm12-1.5c1.25 1.18 1.25 5.82 0 7m2-10c3 2.7 3 10.3 0 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" /></svg>
                `}
                <input type="range" min="0" max="100" step="1" value=${volume} onInput=${changeVolume} className="player-slider min-w-0 flex-1" style=${{ "--fill": `${volume}%` }} aria-label="Trailer volume" />
              </div>
            </div>
          ` : html`
            <button type="button" onClick=${() => setStarted(true)} className="group absolute inset-0 size-full text-left" aria-label="Play the UNBEATABLE trailer on this page">
              <img src="https://i.ytimg.com/vi/XwKFOZeJukA/maxresdefault.jpg" alt="UNBEATABLE trailer thumbnail" className="absolute inset-0 size-full object-cover opacity-80 transition duration-500 group-hover:scale-[1.025] group-hover:opacity-100" />
              <span className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/20"></span>
              <span className="font-unbeatable absolute left-0 top-0 border-b border-r border-paper/50 bg-ink/90 px-4 py-2 text-xs uppercase tracking-[.12em] text-pink sm:px-6 sm:py-3 sm:text-sm">03 / official trailer</span>
              <span className="absolute bottom-5 left-5 sm:bottom-8 sm:left-8">
                <span className="play-badge grid size-16 place-items-center border-2 border-paper bg-pink text-ink shadow-[7px_7px_0_#f0eee8] sm:size-22">
                  <svg viewBox="0 0 24 24" className="ml-1 size-7 sm:size-10" fill="currentColor" aria-hidden="true"><path d="m8 5 11 7-11 7V5Z" /></svg>
                </span>
              </span>
            </button>
          `}
        </div>
      </div>
    `;
}

function GameSection() {
  return html`
      <section id="game" className="site-grid relative scroll-mt-16 overflow-hidden border-b border-white/15 bg-ink sm:scroll-mt-[4.5rem]">
        <div className="font-accent pointer-events-none absolute -right-[4vw] top-[8%] text-[21vw] uppercase leading-none text-white/[.025]" aria-hidden="true">TRAILER</div>
        <div className="graphic-cluster graphic-game" aria-hidden="true"></div>
        <div className="shape-scrap scrap-d bottom-[6%] right-[3%] h-20 w-[18%] rotate-6 bg-pink/15 sm:h-28" aria-hidden="true"></div>
        <div className="shape-scrap scrap-c tone-shift left-[4%] top-[28%] h-28 w-28" aria-hidden="true"></div>
        <div className="relative z-10 mx-auto max-w-[1600px] px-4 py-12 sm:px-7 sm:py-20 lg:py-24">
          <div className="reveal-layer" data-reveal="">
            <h2 className="font-logo whitespace-nowrap text-[clamp(2.8rem,13.5vw,13rem)] uppercase leading-[.8] tracking-[-0.045em]">
              <span className="text-paper">UN</span><span className="italic text-pink">BEAT</span><span className="text-paper">ABLE</span>
            </h2>
          </div>

          <div className="relative mt-7 grid items-end gap-8 sm:mt-10 sm:gap-10 lg:mt-14 lg:grid-cols-[.55fr_1.45fr] lg:gap-14">
            <div className="reveal-layer lg:pb-4" data-reveal="" data-delay="1">
              <p className="font-unbeatable max-w-2xl text-2xl uppercase leading-8 tracking-[.025em] text-white/75 sm:text-3xl sm:leading-9">
                UNBEATABLE is a rhythm adventure where music is illegal and you do crimes. Follow the story of Beat and her band on the run, in a narrative experience full of big emotions powered by arcade-flawless rhythm gameplay.
              </p>
              <div className="mt-8"><${TextLink} href=${STEAM}>UNBEATABLE on Steam<//></div>
            </div>
            <div className="reveal-layer relative mx-auto w-[96%] max-w-[980px] lg:mx-0 lg:ml-auto" data-reveal="">
              <p className="font-unbeatable mb-4 ml-1 text-[9px] uppercase tracking-[.18em] text-white/45 sm:text-[10px]">PLEASE / BUY / THE / GAME / LOL</p>
              <div className="relative">
                <div className="pointer-events-none absolute -inset-3 -rotate-1 border border-pink/45" aria-hidden="true"></div>
                <${Trailer} />
              </div>
            </div>
          </div>
        </div>
      </section>
    `;
}

function Community() {
  return html`
      <section id="community" className="paper-grid relative scroll-mt-16 overflow-hidden bg-lilac text-ink sm:scroll-mt-[4.5rem]">
        <div className="shape-scrap scrap-e bottom-[7%] left-[2%] h-16 w-[20%] -rotate-6 bg-paper/30 sm:h-24" aria-hidden="true"></div>
        <div className="shape-scrap scrap-a tone-shift right-[5%] top-[12%] h-20 w-[14%] rotate-6" aria-hidden="true"></div>
        <div className="relative z-10 mx-auto grid max-w-[1600px] gap-8 px-4 py-14 sm:gap-12 sm:px-7 sm:py-28 lg:grid-cols-[1.2fr_.8fr] lg:items-end lg:py-36">
          <div className="reveal-layer relative" data-reveal="">
            <p className="font-unbeatable text-sm uppercase tracking-[0.12em]">questions / modding / charts</p>
            <h2 className="mt-7 font-display text-[clamp(2.75rem,11vw,10.5rem)] uppercase leading-[0.82] tracking-[-0.075em]">
              MODDING<br /><span className="outline-ink inline-block -skew-x-6">DISCORD</span>
            </h2>
          </div>
          <div className="reveal-layer border-l-4 border-ink pl-5 sm:pl-7" data-reveal="" data-delay="1">
            <p className="font-unbeatable max-w-xl text-xl leading-8 tracking-[.015em] text-ink/70 sm:text-2xl">
              For questions about custom charts, setup, file formats, modding, or something that broke: ask in the UNBEATABLE modding Discord and talk to other charters and modders.
            </p>
            <a href=${DISCORD} target="_blank" rel="noreferrer" className="discord-button mt-8 flex min-h-16 w-full items-center justify-between px-6 py-4 text-paper sm:max-w-md">
              <span className="font-unbeatable relative z-10 text-lg uppercase tracking-[0.1em]">Join modding Discord</span><${Arrow} className="relative z-10 size-7" />
            </a>
          </div>
        </div>
      </section>
    `;
}

function Download() {
  return html`
      <section className="relative overflow-hidden border-y border-white/15 bg-pink text-ink">
        <div className="shape-scrap scrap-f right-[16%] top-[8%] h-16 w-[18%] -rotate-6 bg-paper/30 sm:h-24" aria-hidden="true"></div>
        <a href=${RELEASES} target="_blank" rel="noreferrer" className="group relative z-10 mx-auto grid max-w-[1600px] grid-cols-[1fr_auto] items-center gap-3 px-4 py-7 sm:min-h-64 sm:gap-5 sm:px-7 sm:py-12">
          <div className="reveal-layer" data-reveal="">
            <h2 className="font-display text-[clamp(2.15rem,10vw,9rem)] uppercase leading-[0.86] tracking-[-0.07em]">DOWNLOAD<br /><span className="inline-block -rotate-1 bg-ink px-[.06em] text-paper">CBM EDITOR</span></h2>
          </div>
          <${Arrow} className="size-10 transition-transform duration-200 group-hover:translate-x-1 group-hover:-translate-y-1 sm:size-24 sm:group-hover:translate-x-2 sm:group-hover:-translate-y-2 lg:size-32" />
        </a>
      </section>
    `;
}

function Footer() {
  return html`
      <footer className="bg-ink">
        <div className="mx-auto max-w-[1600px] px-4 py-10 sm:px-7 sm:py-14">
          <div className="grid gap-10 border-b border-white/15 pb-10 md:grid-cols-[1fr_auto]">
            <div>
              <p className="font-logo text-3xl uppercase tracking-[-0.04em] text-pink">CBM EDITOR</p>
              <p className="font-unbeatable mt-3 max-w-xl text-lg leading-6 tracking-[.015em] text-white/50">Highly customizable beatmap editor made for UNBEATABLE</p>
            </div>
            <div className="font-unbeatable flex flex-wrap gap-x-7 gap-y-4 text-sm uppercase tracking-[0.1em]">
              <a href=${RELEASES} target="_blank" rel="noreferrer" className="hover:text-pink">download ↗</a>
              <a href=${REPO} target="_blank" rel="noreferrer" className="hover:text-pink">github ↗</a>
              <a href=${STEAM} target="_blank" rel="noreferrer" className="hover:text-pink">steam ↗</a>
              <a href=${DISCORD} target="_blank" rel="noreferrer" className="hover:text-pink">discord ↗</a>
            </div>
          </div>
          <div className="font-unbeatable mt-6 text-xs uppercase leading-5 tracking-[0.08em] text-white/35">
            <p>Fan made project. Not affiliated or endorsed by D-CELL GAMES or Playstack</p>
          </div>
        </div>
      </footer>
    `;
}

function App() {
  useEffect(() => {
    const intro = document.getElementById("page-intro");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let cancelled = false;
    let readyFrame;
    let fadeFrame;
    let removeIntro;

    const showPage = async () => {
      if (document.fonts) {
        await Promise.allSettled([
          document.fonts.load('1em "Rushford Printed"'),
          document.fonts.load('1em "Variane Craina"'),
          document.fonts.load('1em "Digitag"'),
          document.fonts.load('400 1em "Golos Text"'),
          document.fonts.load('700 1em "Golos Text"'),
          document.fonts.load('400 1em "Fragment Mono"'),
          document.fonts.load('italic 400 1em "Fragment Mono"'),
          document.fonts.load('400 1em "Londrina Solid"')
        ]);
        await document.fonts.ready;
      }

      if (cancelled) return;
      readyFrame = requestAnimationFrame(() => {
        document.documentElement.classList.add("fonts-ready");
        fadeFrame = requestAnimationFrame(() => {
          intro?.classList.add("is-hidden");
          removeIntro = window.setTimeout(() => intro?.remove(), reducedMotion ? 20 : 240);
        });
      });
    };

    showPage();

    return () => {
      cancelled = true;
      cancelAnimationFrame(readyFrame);
      cancelAnimationFrame(fadeFrame);
      window.clearTimeout(removeIntro);
    };
  }, []);

  useEffect(() => {
    const revealBits = Array.from(document.querySelectorAll("[data-reveal]"));
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reducedMotion || !("IntersectionObserver" in window)) {
      revealBits.forEach((item) => item.classList.add("is-visible"));
      return undefined;
    }

    const revealWatcher = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealWatcher.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });

    revealBits.forEach((item) => revealWatcher.observe(item));
    return () => revealWatcher.disconnect();
  }, []);

  return html`
      <${React.Fragment}>
        <${Nav} />
        <main>
          <${Hero} />
          <${WorkflowThingy} />
          <${EditorSection} />
          <${StyleStuff} />
          <${GameSection} />
          <${Community} />
          <${Download} />
        </main>
        <${Footer} />
      <//>
    `;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
