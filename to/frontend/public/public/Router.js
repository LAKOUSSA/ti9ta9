export const checkAccessToken = () => {
	const token = app.utils.getCookie("access_token");
	return !!token;
};

export const refreshLocal = async () => {
	const response = await fetch("http://localhost:8000/api/auth/refresh/", {
		credentials: "include",
		method: "GET",
	});
	const data = await response.json();
	if (response.status === 400) throw new app.utils.AuthError();
	else if (response.status === 403) {
		app.utils.showToast(data.detail);
		throw new app.utils.AuthError();
	}
	app.utils.setCookie("access_token", data.access_token);
};

const handleAuthGuard = async (content, route) => {
	const token = checkAccessToken();
	try {
		if (route.startsWith("/auth")) {
			if (token) return "/";
			await refreshLocal();
			return "/";
		}
		if (content.auth_guard && !token) {
			await refreshLocal();
			console.log("refreshed the token");
			return route;
		}
		return route;
	} catch (error) {
		if (error instanceof app.utils.AuthError) {
			if (route.startsWith("/auth")) return route;
			return "/auth/login";
		}
		console.log("error routing : ", error);
		return "/500";
	}
};


const Router = {
	init: async () => {
		// listen for url changes in history events
		onpopstate = (e) => {
			e.preventDefault();
			const url = e.state ? e.state.url : location.href;
			Router.navigate(url, false);
		};
		// start fresh
		app.utils.removeCookie("access_token");
		await Router.navigate(location.href);
		dispatchEvent(new CustomEvent("navbar-profile"));
		dispatchEvent(new CustomEvent("play-button"));
		dispatchEvent(new CustomEvent("websocket", { detail: { type: "open" } }));
	},
	navigate: async (url, useHistory = true) => {
		const route = new URL(url, window.location.origin).pathname;

		// redirect uknown routes to 404
		if (!app.routes[route]) {
			Router.navigate("/404");
			return;
		}
		// excluding intra and google callback from being added to history

		// handling auth guard
		const render = await handleAuthGuard(app.routes[route], route);
		// special case to replace state in case of navigating through popstate event
		const content = app.routes[render];
		if (useHistory) {
			url = render === route ? url : render;
			console.log("history use");
			render === route
				? history.pushState({ url }, "", url)
				: history.replaceState({ url }, "", url);
		} else {
			// this is always triggered by popstate
			url = render === route ? url : render;
			// replace only if its not allowed, eg: navigating back to home after logout
			if (render !== route) {
				console.log("no history replace", url);
				history.replaceState({ url }, "", url);
			}
		}
		/*
			TODO :
				make sure if you are signing out or something to close the online websocket
		*/

		
		// injecting content in the root div and running the controller
		app.cleanup.map(clean => {
			if (typeof clean === "function")
				clean()
		})
		if (app.cleanup.length !== 0)
			console.log("clean still has something");
		app.cleanup = []
		const root = document.getElementById("root");
		console.log(route);

		while (root.firstChild) root.removeChild(root.firstChild);
		if (content?.style) {
			const loaded = await app.utils.LoadCss(content.style);
			if (!loaded) {
				app.utils.showToast("Failed to load css files");
				app.Router.navigate("/404");
				return;
			}
		}
		root.innerHTML = content.view;

		// disabling default behavior for anchor tags
		const navbar = document.getElementById("nav-bar-outer");
		if (render === "/game" || render === "/xo") navbar.hidden = true;
		else navbar.hidden = false;
		Router.disableReload();
		if (content.controller)
		{
			const clean = await content.controller()
			app.cleanup.push(clean)
		}
	},
	disableReload: () => {
		const a = document.querySelectorAll("a");
		if (!a.length) return;
		a.forEach((tag) => {
			tag.addEventListener("click", (e) => {
				const external = /^(http|https|mailto|ftp):/.test(
					tag.getAttribute("href")
				);
				if (!external) {
					e.preventDefault();
					Router.navigate(tag.getAttribute("href"));
				}
			});
		});
	},
};

export default Router;
