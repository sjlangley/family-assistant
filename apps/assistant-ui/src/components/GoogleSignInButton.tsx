/**
 * Google Sign-In Button Component
 * Uses Google Identity Services to render the sign-in button
 */

import { useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";

export function GoogleSignInButton() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const { loginWithGoogle } = useAuth();
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);

  // Wait for Google Identity Services script to load
  useEffect(() => {
    if (window.google) {
      setIsGoogleLoaded(true);
      return;
    }

    // Poll for Google script availability
    const checkGoogle = setInterval(() => {
      if (window.google) {
        setIsGoogleLoaded(true);
        clearInterval(checkGoogle);
      }
    }, 100);

    return () => clearInterval(checkGoogle);
  }, []);

  // Initialize Google Sign-In button once script is loaded
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

    if (!isGoogleLoaded || !buttonRef.current) {
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
  }, [isGoogleLoaded, loginWithGoogle]);

  return <div ref={buttonRef} data-testid="google-signin-button"></div>;
}
