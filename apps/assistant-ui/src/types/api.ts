/**
 * API types matching the backend User model
 */
export interface User {
  email: string | null;
  userid: string;
  name: string | null;
}

export interface ApiError {
  detail: string;
}
