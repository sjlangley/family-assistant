/**
 * Google Sign-In Button Component
 * Uses Google Identity Services to render the sign-in button
 */

import { useEffect, useRef } from "react";
import { useAuth } from "../lib/auth";

export function GoogleSignInButton() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const { loginWithGoogle } = useAuth();

  useEffect(() => {
    const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

    if (!GOOGLE_CLIENT_ID) {
      console.error(
        "VITE_GOOGLE_CLIENT_ID environment variable is not set. " +
          "Please configure it in your .env file. " +
          "See .env.example for reference.",
      );
      return;
    }

    if (!window.google || !buttonRef.current) {
      return;
    }

    // Initialize Google Identity Services
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: async (response) => {
        try {
          await loginWithGoogle(response.credential);
        } catch (error) {
          console.error("Login error:", error);
        }
      },
    });

    // Render the sign-in button
    window.google.accounts.id.renderButton(buttonRef.current, {
      theme: "outline",
      size: "large",
      text: "signin_with",
    });
  }, [loginWithGoogle]);

  return <div ref={buttonRef} data-testid="google-signin-button"></div>;
}
