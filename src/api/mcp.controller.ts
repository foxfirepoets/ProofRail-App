import { Body, Controller, Headers, HttpException, Post } from "@nestjs/common";
import { ProofRailError } from "../proofrail/errors.js";
import { proofRailService } from "../proofrail/container.js";

@Controller("mcp")
export class McpController {
  @Post("submit_intake")
  async submitIntake(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.submitIntake(body as never, this.actor(authorization)));
  }

  @Post("approve")
  async approve(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.approve(body as never, this.actor(authorization)));
  }

  @Post("reject")
  async reject(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.reject(body as never, this.actor(authorization)));
  }

  @Post("get_gate_status")
  async getGateStatus(): Promise<unknown> {
    return proofRailService.getGateStatus();
  }

  @Post("build_draw")
  async buildDraw(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.buildDraw(body as never, this.actor(authorization)));
  }

  @Post("send_draw")
  async sendDraw(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.sendDraw(body as never, this.actor(authorization)));
  }

  @Post("run_fees")
  async runFees(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.runFees(body as never, this.actor(authorization)));
  }

  @Post("approve_fees")
  async approveFees(@Body() body: unknown, @Headers("authorization") authorization?: string): Promise<unknown> {
    return this.wrap(() => proofRailService.approveFees(body as never, this.actor(authorization)));
  }

  private async wrap(fn: () => Promise<unknown>): Promise<unknown> {
    try {
      return await fn();
    } catch (error) {
      if (error instanceof ProofRailError) {
        throw new HttpException({ error: { code: error.code, message: error.message, detail: error.detail } }, error.status);
      }
      throw error;
    }
  }

  private actor(authorization?: string): string {
    return authorization?.replace(/^Bearer\s+/i, "") || "missing-local-key";
  }
}
