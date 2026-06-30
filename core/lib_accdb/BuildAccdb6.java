import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.util.*;

/**
 * Reshape pre-computed 1n+1 (n=6, target=7) CSV outputs into a real .accdb via
 * Jackcess (pure Java). Reshape ONLY -- no algorithm recomputation.
 *
 * Layout (widened from c545's BuildAccdb):
 *   Input        n1..n6   <- {prefix}.csv  (original rows, canonicalized asc,
 *                                            header auto-skipped if non-numeric)
 *   Grouped      n1..n6   <- {prefix}_1nplus1_grouped.csv cols 0..5 (blanks kept)
 *   NList_Header N1..N7   <- {prefix}_1nplus1_grouped.csv cols 7..13 (blanks kept)
 *   Regenerate   n1..n7   <- {prefix}_1nplus1_regenerate.csv
 *   Remnant      n1..n6   <- {prefix}_1nplus1_remnant.csv
 *
 * args: <prefix> <mode> <out.accdb>
 *   mode = all     -> Input, Grouped, NList_Header, Regenerate, Remnant
 *          core    -> Input, Regenerate, Remnant
 *          grouped -> Grouped
 *          nlist   -> NList_Header
 */
public class BuildAccdb6 {
    static final int BATCH = 20000;
    static final int N = 6, TARGET = 7;

    public static void main(String[] args) throws Exception {
        String prefix = args[0];
        String mode = args[1];
        String out = args[2];
        File outFile = new File(out);
        if (outFile.exists()) outFile.delete();

        Database db = new DatabaseBuilder(outFile)
                .setFileFormat(Database.FileFormat.V2010).create();

        String grouped = prefix + "_1nplus1_grouped.csv";
        String regen   = prefix + "_1nplus1_regenerate.csv";
        String remnant = prefix + "_1nplus1_remnant.csv";
        String input   = prefix + ".csv";

        boolean wantInput = mode.equals("all") || mode.equals("core");
        boolean wantRegen = mode.equals("all") || mode.equals("core");
        boolean wantRem   = mode.equals("all") || mode.equals("core");
        boolean wantGrp   = mode.equals("all") || mode.equals("grouped");
        boolean wantNl    = mode.equals("all") || mode.equals("nlist");

        if (wantInput) {
            Table t = newTable(db, "Input", cols("n", N));
            long c = loadInputCanonical(input, t, N);
            System.out.println("Input=" + c);
        }
        if (wantGrp) {
            Table t = newTable(db, "Grouped", cols("n", N));
            long c = loadGrouped(grouped, t, 0, N, false);
            System.out.println("Grouped=" + c);
        }
        if (wantNl) {
            Table t = newTable(db, "NList_Header", cols("N", TARGET));
            long c = loadGrouped(grouped, t, N + 1, TARGET, false);
            System.out.println("NList_Header=" + c);
        }
        if (wantRegen) {
            Table t = newTable(db, "Regenerate", cols("n", TARGET));
            long c = loadPlain(regen, t, TARGET);
            System.out.println("Regenerate=" + c);
        }
        if (wantRem) {
            Table t = newTable(db, "Remnant", cols("n", N));
            long c = loadPlain(remnant, t, N);
            System.out.println("Remnant=" + c);
        }

        db.flush();
        db.close();
    }

    static String[] cols(String p, int n) {
        String[] c = new String[n];
        for (int i = 0; i < n; i++) c[i] = p + (i + 1);
        return c;
    }

    static Table newTable(Database db, String name, String[] cols) throws IOException {
        TableBuilder tb = new TableBuilder(name);
        for (String c : cols) tb.addColumn(new ColumnBuilder(c, DataType.LONG));
        return tb.toTable(db);
    }

    static Object cell(String s) {
        s = s.trim();
        if (s.isEmpty()) return null;
        return Integer.valueOf(Integer.parseInt(s));
    }

    static boolean isInt(String s) {
        s = s.trim();
        if (s.isEmpty()) return false;
        try { Integer.parseInt(s); return true; } catch (NumberFormatException e) { return false; }
    }

    /** Load original input: first `width` cols, sorted ascending per row, header auto-skipped. */
    static long loadInputCanonical(String path, Table t, int width) throws IOException {
        long count = 0;
        List<Object[]> batch = new ArrayList<>(BATCH);
        try (BufferedReader br = new BufferedReader(new FileReader(path))) {
            String line;
            boolean first = true;
            while ((line = br.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                String[] parts = line.split(",", -1);
                if (first) {
                    first = false;
                    if (!isInt(parts[0])) continue;  // skip a textual header row
                }
                int[] v = new int[width];
                for (int i = 0; i < width; i++) v[i] = Integer.parseInt(parts[i].trim());
                Arrays.sort(v);                       // canonicalize ascending
                Object[] row = new Object[width];
                for (int i = 0; i < width; i++) row[i] = Integer.valueOf(v[i]);
                batch.add(row);
                count++;
                if (batch.size() >= BATCH) { t.addRows(batch); batch.clear(); }
            }
        }
        if (!batch.isEmpty()) t.addRows(batch);
        return count;
    }

    /** Load `width` cols starting at `startCol` from a grouped-style csv (blanks -> NULL). */
    static long loadGrouped(String path, Table t, int startCol, int width, boolean skipBlank)
            throws IOException {
        long count = 0;
        List<Object[]> batch = new ArrayList<>(BATCH);
        try (BufferedReader br = new BufferedReader(new FileReader(path))) {
            br.readLine(); // header
            String line;
            while ((line = br.readLine()) != null) {
                String[] parts = line.split(",", -1);
                Object[] row = new Object[width];
                boolean allNull = true;
                for (int i = 0; i < width; i++) {
                    int idx = startCol + i;
                    Object v = idx < parts.length ? cell(parts[idx]) : null;
                    row[i] = v;
                    if (v != null) allNull = false;
                }
                if (skipBlank && allNull) continue;
                batch.add(row);
                count++;
                if (batch.size() >= BATCH) { t.addRows(batch); batch.clear(); }
            }
        }
        if (!batch.isEmpty()) t.addRows(batch);
        return count;
    }

    /** Load first `width` cols from a simple header+data csv. */
    static long loadPlain(String path, Table t, int width) throws IOException {
        long count = 0;
        List<Object[]> batch = new ArrayList<>(BATCH);
        try (BufferedReader br = new BufferedReader(new FileReader(path))) {
            br.readLine(); // header
            String line;
            while ((line = br.readLine()) != null) {
                if (line.trim().isEmpty()) continue;
                String[] parts = line.split(",", -1);
                Object[] row = new Object[width];
                for (int i = 0; i < width; i++)
                    row[i] = i < parts.length ? cell(parts[i]) : null;
                batch.add(row);
                count++;
                if (batch.size() >= BATCH) { t.addRows(batch); batch.clear(); }
            }
        }
        if (!batch.isEmpty()) t.addRows(batch);
        return count;
    }
}
