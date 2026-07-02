import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function DELETE() {
  try {
    // Delete in order to respect foreign key constraints
    await prisma.$transaction([
      prisma.transcript.deleteMany(),
      prisma.note.deleteMany(),
      prisma.artifact.deleteMany(),
      prisma.screenshot.deleteMany(),
      prisma.auditLog.deleteMany(),
      prisma.aiEmbedding.deleteMany(),
      prisma.sessionTag.deleteMany(),
      prisma.failedExtraction.deleteMany(),
      prisma.session.deleteMany(),
      prisma.patient.deleteMany(),
      prisma.tag.deleteMany(),
      prisma.export.deleteMany(),
    ]);

    return NextResponse.json({ success: true });
  } catch (error: any) {
    console.error('Failed to clear database:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
