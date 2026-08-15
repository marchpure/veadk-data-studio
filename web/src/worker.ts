type Env = {
  ASSETS: {
    fetch: typeof fetch;
  };
};

const CLIENT_ROUTES = ["/share/", "/n/"];

function isClientRoute(pathname: string) {
  return CLIENT_ROUTES.some((prefix) => pathname.startsWith(prefix));
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.hostname === "byaan.ai") {
      url.hostname = "www.byaan.ai";
      return Response.redirect(url.toString(), 301);
    }

    if (isClientRoute(url.pathname)) {
      const assetUrl = new URL(request.url);
      assetUrl.pathname = "/";
      assetUrl.search = "";

      const response = await env.ASSETS.fetch(new Request(assetUrl, request));
      const headers = new Headers(response.headers);
      headers.set("X-Robots-Tag", "noindex, nofollow");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    }

    return new Response("Not found", {
      status: 404,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
      },
    });
  },
};
