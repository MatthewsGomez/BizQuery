import { Request } from "express";

/**
 * Extends the Express Request interface to carry authentication context
 * extracted from the Authorization header.
 */
export interface AuthenticatedRequest extends Request {
  /** Raw JWT token extracted from the Authorization: Bearer <token> header */
  jwtToken: string;
  /** User ID extracted from the JWT sub claim (populated in task 13.1) */
  userId?: string;
}
