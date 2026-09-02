frappe.pages['api_docs'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'API Documentation',
        single_column: true
    });

    // Create the container HTML directly in the page body
    page.body.html(`
		<div class="api-docs-wrapper" style="background-color: #FAFAF9; min-height: 100vh; padding: 2rem;">
			<div class="api-docs-container" style="max-width: 1400px; margin: 0 auto;">
				<div class="api-docs-header" style="margin-bottom: 2rem;">
					<h1 style="font-family: serif; color: #3F3F46; font-weight: 500; font-size: 2rem; margin-bottom: 0.5rem;">API Documentation</h1>
					<p style="color: #71717A; font-size: 0.95rem;">Interactive API testing interface for rndopsapp endpoints</p>
				</div>
				<div id="swagger-ui" style="background-color: #FFFFFF; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);"></div>
			</div>
		</div>
	`);

    // Load Swagger UI assets from CDN
    const swaggerUICSS = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css';
    const swaggerUIBundle = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js';
    const swaggerUIStandalone = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js';

    // Load CSS
    if (!document.querySelector(`link[href="${swaggerUICSS}"]`)) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = swaggerUICSS;
        document.head.appendChild(link);
    }

    // Load JS libraries
    const loadScript = (src) => {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${src}"]`)) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    };

    // Initialize Swagger UI after scripts load
    Promise.all([
        loadScript(swaggerUIBundle),
        loadScript(swaggerUIStandalone)
    ]).then(() => {
        initializeSwaggerUI(page);
    }).catch((error) => {
        frappe.msgprint({
            title: __('Error'),
            indicator: 'red',
            message: __('Failed to load Swagger UI libraries. Please check your internet connection.')
        });
        console.error('Swagger UI load error:', error);
    });
};

function initializeSwaggerUI(page) {
    // Fetch the OpenAPI schema from our backend
    frappe.call({
        method: 'rndopsapp.rndopsapp.api_docs.get_api_schema',
        callback: function (r) {
            if (r.message) {
                // Verify the container exists
                const container = document.getElementById('swagger-ui');
                if (!container) {
                    console.error('Swagger UI container not found!');
                    frappe.msgprint({
                        title: __('Error'),
                        indicator: 'red',
                        message: __('Failed to initialize API Documentation. Container not found.')
                    });
                    return;
                }

                // Initialize Swagger UI
                const ui = SwaggerUIBundle({
                    spec: r.message,
                    dom_id: '#swagger-ui',
                    deepLinking: true,
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIStandalonePreset
                    ],
                    plugins: [
                        SwaggerUIBundle.plugins.DownloadUrl
                    ],
                    layout: "StandaloneLayout",
                    // Custom request interceptor to add Frappe CSRF token
                    requestInterceptor: (request) => {
                        // Add CSRF token for Frappe
                        request.headers['X-Frappe-CSRF-Token'] = frappe.csrf_token;

                        // If using API key auth, it's already in Authorization header
                        // Otherwise, use session-based auth (cookies)

                        return request;
                    },
                    // Response interceptor for debugging
                    responseInterceptor: (response) => {
                        return response;
                    }
                });

                window.ui = ui;
                console.log('Swagger UI initialized successfully');
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: __('Failed to load API schema.')
                });
            }
        },
        error: function (err) {
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('Failed to fetch API documentation. Please check console for details.')
            });
            console.error('API Schema fetch error:', err);
        }
    });
}
