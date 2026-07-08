import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module.js";
import { applyDatabaseUrlAliases } from "../env.js";

async function bootstrap(): Promise<void> {
  applyDatabaseUrlAliases();
  const app = await NestFactory.create(AppModule);
  app.enableShutdownHooks();
  await app.listen(process.env.PORT ? Number(process.env.PORT) : 3001);
}

await bootstrap();
