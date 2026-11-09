#ifndef UTIL_HPP
#define UTIL_HPP

#include <string>
#include <vector>
#include <numeric>
#include <algorithm>
#include <sstream>
#include <cmath>

namespace util {
    // Replace boost::erase_all
    inline void erase_all(std::string& str, const std::string& to_erase) {
        size_t pos = 0;
        while ((pos = str.find(to_erase, pos)) != std::string::npos) {
            str.erase(pos, to_erase.length());
        }
    }

    // Replace boost::tokenizer
    inline std::vector<std::string> tokenize(const std::string& str, char delimiter) {
        std::vector<std::string> tokens;
        std::istringstream stream(str);
        std::string token;
        while (std::getline(stream, token, delimiter)) {
            tokens.push_back(token);
        }
        return tokens;
    }

    // Parse integers from a comma-separated string
    inline std::vector<int> parse_int_list(const std::string& str, char delimiter = ',') {
        std::vector<int> result;
        std::istringstream stream(str);
        std::string token;
        
        while (std::getline(stream, token, delimiter)) {
            // Remove any spaces
            token.erase(std::remove_if(token.begin(), token.end(), ::isspace), token.end());
            if (!token.empty()) {
                result.push_back(std::stoi(token));
            }
        }
        
        return result;
    }

    // Statistics namespace to replace boost::accumulators
    namespace stats {
        template<typename T>
        double mean(const std::vector<T>& data) {
            if (data.empty()) return 0.0;
            return std::accumulate(data.begin(), data.end(), 0.0) / data.size();
        }

        template<typename T>
        double variance(const std::vector<T>& data) {
            if (data.size() <= 1) return 0.0;
            double m = mean(data);
            double sum = 0.0;
            for (const auto& val : data) {
                sum += (val - m) * (val - m);
            }
            return sum / data.size();
        }

        template<typename T>
        double standard_deviation(const std::vector<T>& data) {
            return std::sqrt(variance(data));
        }
    }
}

#endif /* UTIL_HPP */