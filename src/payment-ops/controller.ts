import { Body, Controller, Get, Headers, HttpException, Param, Post } from "@nestjs/common";
import { PaymentOpsError } from "./errors.js";
import { PaymentOpsService } from "./service.js";
import { AuthenticatedPrincipal, PrincipalAuthenticator } from "./types.js";
import { Inject } from "@nestjs/common";
import { PAYMENT_OPS_AUTHENTICATOR } from "./types.js";

@Controller()
export class PaymentOpsController {
  constructor(private readonly service: PaymentOpsService, @Inject(PAYMENT_OPS_AUTHENTICATOR) private readonly authenticate: PrincipalAuthenticator | undefined) {}

  @Post("payment-obligations") create(@Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.createAsync(body, await this.principal(auth))); }
  @Get("payment-obligations") list() { return this.wrap(() => this.service.listAsync()); }
  @Post("payment-obligations/:id/verify") verify(@Param("id") id: string, @Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.verifyAsync(id, body, await this.principal(auth))); }
  @Post("payment-obligations/:id/request-approval") requestApproval(@Param("id") id: string, @Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.requestApprovalAsync(id, body, await this.principal(auth))); }
  @Post("payment-obligations/:id/mark-unavailable") unavailable(@Param("id") id: string, @Body() body: { reason: string; fallbackTaskRef?: string }, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.markUnavailableAsync(id, body.reason, await this.principal(auth), body.fallbackTaskRef)); }
  @Post("payment-obligations/:id/mark-scheduled") scheduled(@Param("id") id: string, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.markScheduledAsync(id, await this.principal(auth))); }
  @Post("payment-obligations/:id/mark-paid") paid(@Param("id") id: string, @Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.markPaidAsync(id, body, await this.principal(auth))); }
  @Post("payment-obligations/:id/clear") clear(@Param("id") id: string, @Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.clearAsync(id, body, await this.principal(auth))); }
  @Post("payment-obligations/:id/reconcile") reconcile(@Param("id") id: string, @Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => this.service.reconcileAsync(id, body, await this.principal(auth))); }
  @Post("non-bill-outflows") nonBill(@Body() body: any, @Headers("authorization") auth?: string) { return this.wrap(async () => { await this.principal(auth); return this.service.createNonBillAsync(body); }); }
  @Get("non-bill-outflows") listNonBill() { return this.wrap(() => this.service.listNonBillAsync()); }

  private async wrap<T>(fn: () => T | Promise<T>): Promise<T> { try { return await fn(); } catch (error) { if (error instanceof PaymentOpsError) throw new HttpException({ error: { code: error.code, message: error.message, missingGates: error.missingGates } }, error.status); throw error; } }
  private async principal(auth?: string): Promise<AuthenticatedPrincipal> {
    if (!this.authenticate) throw new HttpException({ error: { code: "AUTHENTICATION_PROVIDER_UNAVAILABLE", message: "A verified authentication provider is required" } }, 503);
    const principal = await this.authenticate(auth);
    if (!principal?.verified || !principal.id?.trim() || !principal.issuer?.trim() || !principal.roles.includes("payment-ops")) throw new HttpException({ error: { code: "AUTHENTICATION_REQUIRED", message: "A server-verified payment-ops principal is required" } }, 401);
    return principal;
  }
}
