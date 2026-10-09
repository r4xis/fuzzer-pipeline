FROM aflplusplus/aflplusplus:latest

RUN apt-get update && apt-get install -y \
    cmake \
    git \
    gdb \
    && rm -rf /var/lib/apt/lists/*

# CASR for crash triage - base image already has Rust/cargo installed
RUN cargo install casr

WORKDIR /fuzzing
RUN git clone https://github.com/libgme/game-music-emu.git /src/libgme
RUN cd /src/libgme && \
    cmake -DCMAKE_CXX_COMPILER=afl-c++ \
          -DCMAKE_C_COMPILER=afl-cc \
          -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/fuzzing/libgme_inst . && \
    make -j$(nproc) && \
    make install

COPY harness/fuzz_nsf.cpp /fuzzing/
RUN afl-c++ -O3 -o /fuzzing/harness /fuzzing/fuzz_nsf.cpp \
    -I/fuzzing/libgme_inst/include \
    -L/fuzzing/libgme_inst/lib \
    -lgme -lstdc++ \
    -Wl,-rpath,/fuzzing/libgme_inst/lib \
    -fsanitize=fuzzer,address \
    -fno-omit-frame-pointer

VOLUME ["/data"]
