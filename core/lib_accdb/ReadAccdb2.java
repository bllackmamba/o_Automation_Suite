import com.healthmarketscience.jackcess.*;
import java.io.*;
import java.util.*;

/** Reopen an .accdb and dump every table's row count + first 5 rows. */
public class ReadAccdb2 {
    public static void main(String[] args) throws Exception {
        String path = args[0];
        Database db = DatabaseBuilder.open(new File(path));
        System.out.println("opened OK: " + path);
        System.out.println("tables: " + db.getTableNames());
        for (String name : db.getTableNames()) {
            Table t = db.getTable(name);
            System.out.println("\n=== " + name + " (rows=" + t.getRowCount() + ") cols="
                    + colNames(t));
            int shown = 0;
            for (Row r : t) {
                System.out.println("  " + r.values());
                if (++shown >= 5) break;
            }
        }
        db.close();
    }

    static List<String> colNames(Table t) {
        List<String> out = new ArrayList<>();
        for (Column c : t.getColumns()) out.add(c.getName());
        return out;
    }
}
