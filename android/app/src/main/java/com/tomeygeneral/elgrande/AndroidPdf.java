package com.tomeygeneral.elgrande;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.pdf.PdfDocument;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/** Android-native PDF invoice output, without a separate native Python PDF wheel. */
public final class AndroidPdf {
    private AndroidPdf() { }

    public static void render(String path, int number, String customer, String phone,
            String location, String equipment, String service, String issue, String work,
            String total, String issuedAt) throws IOException {
        PdfDocument document = new PdfDocument();
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        int page = 0;
        Canvas canvas = null;
        float y = 0;
        try {
            List<String> lines = new ArrayList<>();
            lines.add("INVOICE   ABD-" + String.format(java.util.Locale.US, "%06d", number));
            lines.add("CUSTOMER: " + customer);
            if (!phone.isEmpty()) lines.add("PHONE: " + phone);
            if (!location.isEmpty()) lines.add("LOCATION: " + location);
            if (!equipment.isEmpty()) lines.add("VEHICLE / JOB: " + equipment);
            lines.add("ISSUED: " + issuedAt.substring(0, Math.min(10, issuedAt.length())));
            lines.add("");
            lines.add("COMPLETED WORK");
            lines.add(service);
            lines.add(issue);
            lines.add(work);
            lines.add("");
            lines.add("TOTAL INVOICE: $" + total);
            lines.add("Agreed customer price. No separate tax is added.");
            lines.add("Please retain this invoice for your records.");

            for (int i = -1; i < lines.size(); i++) {
                if (canvas == null || y > 730) {
                    if (canvas != null) document.finishPage(current);
                    current = document.startPage(new PdfDocument.PageInfo.Builder(612, 792, ++page).create());
                    canvas = current.getCanvas();
                    paint.setColor(Color.rgb(18, 63, 62));
                    canvas.drawRect(0, 0, 612, 100, paint);
                    paint.setColor(Color.WHITE);
                    paint.setTextSize(23);
                    paint.setFakeBoldText(true);
                    canvas.drawText("ALL BY DEVOLL", 40, 52, paint);
                    paint.setTextSize(11);
                    paint.setFakeBoldText(false);
                    canvas.drawText("Mobile repair and service  |  Manistee, Michigan", 42, 75, paint);
                    y = 135;
                }
                if (i == -1) continue;
                String line = lines.get(i).replaceAll("[\\r\\n]+", " ").trim();
                if (line.isEmpty()) { y += 12; continue; }
                boolean heading = line.startsWith("TOTAL INVOICE") ||
                                  line.equals("COMPLETED WORK") || line.startsWith("INVOICE ");
                paint.setColor(Color.rgb(18, 63, 62));
                paint.setTextSize(heading ? 15 : 11);
                paint.setFakeBoldText(heading);
                for (String part : wrap(line, paint, 515)) {
                    if (y > 740) {
                        document.finishPage(current);
                        current = document.startPage(new PdfDocument.PageInfo.Builder(612, 792, ++page).create());
                        canvas = current.getCanvas();
                        y = 52;
                    }
                    canvas.drawText(part, 42, y, paint);
                    y += heading ? 24 : 18;
                }
                if (heading) y += 8;
            }
            if (canvas != null) document.finishPage(current);
            File output = new File(path);
            try (FileOutputStream stream = new FileOutputStream(output)) {
                document.writeTo(stream);
            }
        } finally {
            document.close();
        }
    }

    private static PdfDocument.Page current;

    private static List<String> wrap(String text, Paint paint, float width) {
        List<String> result = new ArrayList<>();
        StringBuilder line = new StringBuilder();
        for (String word : text.split("\\s+")) {
            String next = line.length() == 0 ? word : line + " " + word;
            if (paint.measureText(next) > width && line.length() > 0) {
                result.add(line.toString());
                line = new StringBuilder(word);
            } else {
                line = new StringBuilder(next);
            }
        }
        if (line.length() > 0) result.add(line.toString());
        return result;
    }
}
