import { Module } from "@nestjs/common";
import { PaymentOpsController } from "./controller.js";
import { PaymentOpsService } from "./service.js";
import { PrismaPaymentOpsRepository, PaymentOpsRepository } from "./repository.js";
import { PAYMENT_OPS_AUTHENTICATOR, PrincipalAuthenticator } from "./types.js";

export const PAYMENT_OPS_REPOSITORY = Symbol("PAYMENT_OPS_REPOSITORY");

function durableRepository(): PaymentOpsRepository {
  if (!process.env.DATABASE_URL?.trim()) {
    throw new Error("PAYMENT_OPS_DURABLE_REPOSITORY_REQUIRED: DATABASE_URL is not configured");
  }
  return new PrismaPaymentOpsRepository();
}

@Module({
  controllers: [PaymentOpsController],
  providers: [
    { provide: PAYMENT_OPS_AUTHENTICATOR, useFactory: (): PrincipalAuthenticator | undefined => undefined },
    { provide: PAYMENT_OPS_REPOSITORY, useFactory: durableRepository },
    { provide: PaymentOpsService, useFactory: (repository: PaymentOpsRepository) => new PaymentOpsService(repository, true, process.env.PAYMENT_OPS_APPROVER_ID?.trim()), inject: [PAYMENT_OPS_REPOSITORY] },
  ],
  exports: [PaymentOpsService],
})
export class PaymentOpsModule {}
