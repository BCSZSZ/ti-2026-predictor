package ti.replay;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import skadistats.clarity.io.Util;
import skadistats.clarity.model.DTClass;
import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.processor.entities.Entities;
import skadistats.clarity.processor.entities.UsesEntities;
import skadistats.clarity.processor.reader.OnTickStart;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;

public final class FantasyReplayParser {
    private static final String PARSER_VERSION = "p1-native-v1";
    private static final String RADIANT_CLASS = "CDOTA_DataRadiant";
    private static final String DIRE_CLASS = "CDOTA_DataDire";
    private static final Map<String, String> FIELD_PATHS = createFieldPaths();
    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();

    private Entity radiantData;
    private Entity direData;
    private String engine;
    private int buildNumber;
    private int gameVersion;
    private int lastTick;

    private FantasyReplayParser() {}

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("usage: java -jar ti-replay-parser.jar <decompressed.dem>");
            System.exit(2);
        }

        Path replayPath = Path.of(args[0]).toAbsolutePath().normalize();
        try {
            if (!Files.isRegularFile(replayPath)) {
                throw new IOException("replay file not found: " + replayPath);
            }
            Result result = parse(replayPath);
            System.out.println(GSON.toJson(result));
        } catch (Exception error) {
            Failure failure = new Failure(PARSER_VERSION, error.getClass().getSimpleName(), error.getMessage());
            System.err.println(GSON.toJson(failure));
            System.exit(1);
        }
    }

    static Result parse(Path replayPath) throws IOException, NoSuchAlgorithmException {
        long started = System.nanoTime();
        FantasyReplayParser processor = new FantasyReplayParser();
        try (MappedFileSource source = new MappedFileSource(replayPath)) {
            new SimpleRunner(source).runWith(processor);
        }

        List<PlayerRow> players = new ArrayList<>();
        processor.appendTeam(players, processor.radiantData, 0, "radiant");
        processor.appendTeam(players, processor.direData, 128, "dire");
        players.sort(Comparator.comparingInt(row -> row.playerSlot));

        String replaySha256 = sha256(replayPath);
        String schemaFingerprint = processor.schemaFingerprint();
        long durationMs = Math.round((System.nanoTime() - started) / 1_000_000.0);
        return new Result(
                PARSER_VERSION,
                replaySha256,
                processor.engine,
                processor.buildNumber,
                processor.gameVersion,
                processor.lastTick,
                schemaFingerprint,
                durationMs,
                players);
    }

    @UsesEntities
    @OnTickStart
    public void onTickStart(Context context, boolean synthetic) {
        if (synthetic) {
            return;
        }
        Entities entities = context.getProcessor(Entities.class);
        Entity currentRadiant = entities.getByDtName(RADIANT_CLASS);
        Entity currentDire = entities.getByDtName(DIRE_CLASS);
        if (currentRadiant != null) {
            radiantData = currentRadiant;
        }
        if (currentDire != null) {
            direData = currentDire;
        }
        engine = context.getEngineType().getId().name();
        buildNumber = context.getBuildNumber();
        gameVersion = context.getGameVersion();
        lastTick = context.getTick();
    }

    private void appendTeam(List<PlayerRow> output, Entity entity, int slotOffset, String team) {
        for (int teamSlot = 0; teamSlot < 5; teamSlot++) {
            LinkedHashMap<String, Observation> stats = new LinkedHashMap<>();
            for (Map.Entry<String, String> field : FIELD_PATHS.entrySet()) {
                stats.put(field.getKey(), observe(entity, field.getValue(), teamSlot));
            }
            output.add(new PlayerRow(slotOffset + teamSlot, team, teamSlot, entity != null, stats));
        }
    }

    private Observation observe(Entity entity, String template, int teamSlot) {
        if (entity == null) {
            return new Observation(false, false, null);
        }
        String path = template.replace("%i", Util.arrayIdxToString(teamSlot));
        DTClass dataClass = entity.getDtClass();
        FieldPath fieldPath = dataClass.getFieldPathForName(path);
        if (fieldPath == null) {
            return new Observation(false, false, null);
        }

        boolean observed = observedPaths(entity).contains(path);
        if (!observed) {
            return new Observation(true, false, null);
        }
        Object raw = entity.getPropertyForFieldPath(fieldPath);
        if (!(raw instanceof Number number)) {
            return new Observation(true, true, null);
        }
        return new Observation(true, true, number.intValue());
    }

    private Set<String> observedPaths(Entity entity) {
        Set<String> names = new HashSet<>();
        if (entity == null || entity.getState() == null) {
            return names;
        }
        Iterator<FieldPath> iterator = entity.getState().fieldPathIterator();
        while (iterator.hasNext()) {
            FieldPath path = iterator.next();
            String name = entity.getDtClass().getNameForFieldPath(path);
            if (name != null) {
                names.add(name);
            }
        }
        return names;
    }

    private String schemaFingerprint() throws NoSuchAlgorithmException {
        List<String> material = new ArrayList<>();
        material.add("engine=" + engine);
        material.add("build=" + buildNumber);
        material.add("game=" + gameVersion);
        appendSchemaMaterial(material, radiantData, RADIANT_CLASS);
        appendSchemaMaterial(material, direData, DIRE_CLASS);
        material.sort(String::compareTo);
        return sha256(String.join("\n", material).getBytes(StandardCharsets.UTF_8));
    }

    private void appendSchemaMaterial(List<String> material, Entity entity, String expectedClass) {
        material.add("entity=" + expectedClass + ":" + (entity != null));
        if (entity == null) {
            return;
        }
        DTClass dataClass = entity.getDtClass();
        for (String template : FIELD_PATHS.values()) {
            for (int teamSlot = 0; teamSlot < 5; teamSlot++) {
                String path = template.replace("%i", Util.arrayIdxToString(teamSlot));
                FieldPath fieldPath = dataClass.getFieldPathForName(path);
                material.add(dataClass.getDtName() + ":" + path + ":" + (fieldPath == null ? "absent" : fieldPath));
            }
        }
    }

    private static Map<String, String> createFieldPaths() {
        LinkedHashMap<String, String> fields = new LinkedHashMap<>();
        fields.put("madstone_collected", "m_vecDataTeam.%i.m_iNeutralTokensFound");
        fields.put("smokes_used", "m_vecDataTeam.%i.m_iSmokesUsed");
        fields.put("watchers_taken", "m_vecDataTeam.%i.m_iWatchersTaken");
        fields.put("lotuses_gained", "m_vecDataTeam.%i.m_iLotusesTaken");
        fields.put("tormentor_kills", "m_vecDataTeam.%i.m_iTormentorKills");
        return fields;
    }

    private static String sha256(Path path) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[1024 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return hex(digest.digest());
    }

    private static String sha256(byte[] value) throws NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        return hex(digest.digest(value));
    }

    private static String hex(byte[] value) {
        StringBuilder output = new StringBuilder(value.length * 2);
        for (byte item : value) {
            output.append(String.format("%02x", item));
        }
        return output.toString();
    }

    private record Observation(boolean schemaPresent, boolean observed, Integer value) {}

    private record PlayerRow(
            int playerSlot,
            String team,
            int teamSlot,
            boolean entityPresent,
            Map<String, Observation> stats) {}

    private record Result(
            String parserVersion,
            String replaySha256,
            String engine,
            int buildNumber,
            int gameVersion,
            int lastTick,
            String schemaFingerprint,
            long durationMs,
            List<PlayerRow> players) {}

    private record Failure(String parserVersion, String errorType, String message) {}
}
