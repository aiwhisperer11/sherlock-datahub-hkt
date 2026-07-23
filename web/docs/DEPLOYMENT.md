# Deployment Notes

The application uses standard Next.js conventions and is compatible with Vercel, but no deployment configuration, project linkage, or deployment has been created.

Before deployment, provide `NEXT_PUBLIC_SHERLOCK_API_URL` for the deployed backend and configure the backend's `SHERLOCK_CORS_ORIGINS` with the frontend origin. Never place credentials in public Next.js environment variables.

The demo endpoint currently serves a labelled sandbox fixture. A future production deployment must show whether an investigation was sourced from live DataHub or a fallback snapshot.
