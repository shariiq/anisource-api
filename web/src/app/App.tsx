import { A, Route, Router } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";
import { lazy, Suspense, type ParentComponent } from "solid-js";
import "~/styles/global.css";
import "./App.css";

const Home = lazy(() => import("~/routes/Home"));
const Browse = lazy(() => import("~/routes/Browse"));
const Detail = lazy(() => import("~/routes/Detail"));
const Schedule = lazy(() => import("~/routes/Schedule"));
const MyList = lazy(() => import("~/routes/MyList"));
const Watch = lazy(() => import("~/routes/Watch"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const Shell: ParentComponent = (props) => (
  <div class="app-shell">
    <header class="site-header page-shell">
      <A class="brand" href="/" aria-label="AniSource home">
        <span class="brand-mark">A</span>
        <span class="brand-name">AniSource</span>
      </A>
      <nav class="site-nav" aria-label="Primary navigation">
        <A href="/browse">Browse</A>
        <A href="/schedule">Schedule</A>
        <A href="/my-list">My List</A>
      </nav>
      <A class="search-link" href="/browse?focus=search" aria-label="Search">
        ⌕
      </A>
    </header>
    <main>
      <Suspense fallback={<div class="route-loading page-shell">Loading…</div>}>{props.children}</Suspense>
    </main>
    <footer class="site-footer page-shell">
      <span>AniSource</span>
      <span class="muted">Discovery by AniList · Playback when you choose</span>
    </footer>
  </div>
);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router root={Shell}>
        <Route path="/" component={Home} />
        <Route path="/browse" component={Browse} />
        <Route path="/search" component={Browse} />
        <Route path="/anime/:id" component={Detail} />
        <Route path="/schedule" component={Schedule} />
        <Route path="/my-list" component={MyList} />
        <Route path="/list" component={MyList} />
        <Route path="/watch/:id" component={Watch} />
        <Route path="*404" component={Home} />
      </Router>
    </QueryClientProvider>
  );
}
