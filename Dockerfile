FROM aflplusplus/aflplusplus:latest

RUN apt-get update && apt-get install -y \
    cmake \
    git \
    libgme-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /fuzzing

# libgme'yi AFL++ ile instrumentlu derle
RUN git clone https://github.com/libgme/game-music-emu.git /src/libgme
RUN cd /src/libgme && \
    cmake -DCMAKE_CXX_COMPILER=afl-c++ \
          -DCMAKE_C_COMPILER=afl-cc \
          -DCMAKE_BUILD_TYPE=Release . && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# Harness'ı derle
COPY harness/fuzz_nsf.cpp /fuzzing/
RUN afl-c++ -o /fuzzing/harness /fuzzing/fuzz_nsf.cpp \
    -lgme -lstdc++ \
    -fsanitize=fuzzer,address \
    -fno-omit-frame-pointer

VOLUME ["/data"]

CMD ["sh", "-c", \
    "afl-fuzz -i /data/seeds_min -o /data/afl-output -M fuzzer0 -- /fuzzing/harness @@"]
